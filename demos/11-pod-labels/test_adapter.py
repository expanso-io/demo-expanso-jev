import copy
import importlib.util
import json
import io
import http.client
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "adapter", Path(__file__).with_name("adapter.py")
)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def pod(name="target", labels=None, namespace="demo"):
    return {
        "metadata": {
            "namespace": namespace,
            "name": name,
            "uid": "uid-" + name,
            "resourceVersion": "1",
            "labels": labels or {},
            "annotations": {},
        },
        "spec": {"containers": [{"name": "web", "image": "nginx"}]},
    }


def candidate(target=None):
    return a.candidates(
        [target or pod(), pod("source", {"team": "payments"}, "other")], {"demo"}
    )[0]


def apply_patch(target, operations):
    updated = copy.deepcopy(target)
    updated["metadata"]["labels"] = operations[2]["value"]
    updated["metadata"]["annotations"] = operations[3]["value"]
    updated["metadata"]["resourceVersion"] = "2"
    return updated


class FakeKube:
    def __init__(self):
        self.target = pod()
        self.patches = []

    def logs(self, namespace, name):
        return ["synthetic_stimulus checkout_completed"]

    def event(self, namespace, name, scenario):
        return {"scenario": scenario}

    def pods(self):
        return [self.target, pod("source", {"team": "payments"}, "other")]

    def get(self, namespace, name):
        return copy.deepcopy(self.target)

    def patch(self, namespace, name, operations):
        self.patches.append(operations)
        self.target = apply_patch(self.target, operations)
        return self.target


class Tests(unittest.TestCase):
    def setUp(self):
        # Unit tests must never query a live network inherited from .env.
        environment = patch.dict(a.os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def owned_engine(self, name="checkout-api"):
        e = self.engine()
        e.kube.target = pod(name)
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/fixture"] = "visual-v1"
        return e

    def noise_engine(self):
        e = self.owned_engine()
        e.namespaces = {"jev-label-demo"}
        e.kube.target["metadata"]["namespace"] = "jev-label-demo"
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/workload-version"] = (
            "signals-v6"
        )
        return e

    def test_cloud_routine_reads_once_without_judgment_or_mutation(self):
        e = self.noise_engine()
        line = json.dumps({"event": "routine_heartbeat", "at": 1})
        with patch.object(e.kube, "logs", return_value=[line]) as logs:
            with patch.object(e, "judge") as judge:
                self.assertEqual(e.collect_routine(mode="general"), [])
                self.assertEqual(e.events[-1]["stage"], "routine")
                self.assertEqual(e.events[-1]["count"], 1)
                self.assertEqual(e.events[-1]["logs"], [line])
                self.assertEqual(e.collect_routine(mode="general"), [])
                self.assertEqual(len(e.events), 1)
                judge.assert_not_called()
            self.assertEqual(logs.call_count, 2)
        self.assertEqual(e.pending, {})
        self.assertEqual(e.kube.patches, [])

    def test_routine_delivery_continues_during_pending_jev(self):
        e = self.noise_engine()
        token = e.snapshot()[0]["id"]
        started, release = threading.Event(), threading.Event()
        failures = []

        def response(*args, **kwargs):
            started.set()
            if not release.wait(3):
                raise TimeoutError("test did not release Jev")
            return io.BytesIO(b'{"answers":{"act":{"noul":0.95}}}')

        def judge():
            try:
                e.judge(token)
            except Exception as exc:
                failures.append(exc)

        e.general_log = a.logging.StreamHandler(io.StringIO())
        with patch.object(a.urllib.request, "urlopen", side_effect=response):
            worker = threading.Thread(target=judge)
            worker.start()
            try:
                self.assertTrue(started.wait(1))
                with patch.object(
                    e.kube,
                    "logs",
                    return_value=[json.dumps({"event": "routine_heartbeat", "at": 1})],
                ):
                    e.collect_routine(mode="general")
                self.assertEqual(e.events[-1]["destination"], "general_logs")
                self.assertTrue(worker.is_alive())
            finally:
                release.set()
                worker.join(3)
        self.assertEqual(failures, [])
        stages = [event["stage"] for event in e.events]
        self.assertLess(stages.index("judging"), stages.index("routine"))
        self.assertLess(stages.index("routine"), stages.index("judged"))

    def test_general_logs_are_written_once_before_receipt(self):
        e = self.noise_engine()
        output = io.StringIO()
        e.general_log = a.logging.StreamHandler(output)
        line = json.dumps({"event": "routine_heartbeat", "at": 1})
        with patch.object(e.kube, "logs", return_value=[line]):
            e.collect_routine()
            e.collect_routine()
        records = [json.loads(row) for row in output.getvalue().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["log"], line)
        self.assertEqual(e.events[-1]["destination"], "general_logs")
        self.assertEqual(e.pending, {})

    def test_failed_general_log_has_no_delivery_receipt(self):
        e = self.noise_engine()
        e.general_log = a.logging.StreamHandler(io.StringIO())
        line = json.dumps({"event": "routine_heartbeat", "at": 1})
        with (
            patch.object(e.kube, "logs", return_value=[line]),
            patch.object(e.general_log, "emit", side_effect=OSError("disk full")),
        ):
            with self.assertRaises(OSError):
                e.collect_routine()
        self.assertEqual(e.events, [])
        self.assertEqual(e.routine_seen, {})

    def test_native_routine_collects_changed_logs_without_injected_event(self):
        e = self.noise_engine()
        e.kube.target["metadata"]["annotations"].clear()
        with patch.object(e.kube, "logs", return_value=["new evidence"]) as logs:
            items = e.collect_routine()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["candidate"]["pod"]["logs"], ["new evidence"])
            logs.assert_called_once_with("jev-label-demo", "checkout-api")
            self.assertEqual(e.collect_routine(), [])
            e.kube.target["metadata"]["uid"] = "replacement"
            self.assertEqual(len(e.collect_routine()), 1)
        with patch.object(e.kube, "logs", return_value=["changed again"]):
            self.assertEqual(len(e.collect_routine()), 1)
        self.assertEqual(e.kube.patches, [])

    def test_native_collection_is_bounded_and_prunes_deleted_pods(self):
        e = self.engine()
        other = pod("second")
        source = pod("source", {"team": "payments"}, "other")
        with patch.object(e.kube, "pods", return_value=[e.kube.target, other, source]):
            first = e.collect_routine()
            second = e.collect_routine()
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
            self.assertNotEqual(
                first[0]["candidate"]["pod"]["uid"],
                second[0]["candidate"]["pod"]["uid"],
            )
            self.assertEqual(e.collect_routine(), [])
        with patch.object(e.kube, "pods", return_value=[]):
            self.assertEqual(e.collect_routine(), [])
        self.assertEqual(e.native_seen, {})
        self.assertEqual(e.log_cache, {})

    def test_v7_catalog_origin_and_observed_inventory_preserve_sources(self):
        e = self.noise_engine()
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/workload-version"] = (
            "signals-v7"
        )
        source = pod("batch-source", {"routing-tier": "batch"}, "other")
        with patch.object(e.kube, "pods", return_value=[e.kube.target, source]):
            self.assertTrue(a.ordinary_fixture(e.kube.target))
            options = a.candidates(e.kube.pods(), e.namespaces)
            observed = next(c for c in options if c["value"] == "batch")
            configured = next(c for c in options if c["value"] == "stable")
            self.assertEqual(observed["origin"], "observed")
            self.assertEqual(observed["sources"][0]["uid"], "uid-batch-source")
            self.assertEqual(configured["origin"], "configured")
            self.assertEqual(
                e.state()["observed_label_inventory"],
                [
                    {
                        "key": "routing-tier",
                        "value": "batch",
                        "source_pods": [
                            {
                                "namespace": "other",
                                "name": "batch-source",
                                "uid": "uid-batch-source",
                            }
                        ],
                    }
                ],
            )
        e.kube.target["metadata"]["labels"] = {"routing-tier": "batch"}
        options = a.candidates([e.kube.target], e.namespaces)
        self.assertFalse(any(c["operation"] == "undo" for c in options))

    def test_investigation_scenarios_rejected_by_normal_stimulus(self):
        e = self.noise_engine()
        for scenario in (
            "investigate_restart",
            "investigate_context",
            "investigate_evidence",
        ):
            with self.assertRaises(ValueError):
                e.stimulus(
                    {
                        "namespace": "jev-label-demo",
                        "pod": "checkout-api",
                        "scenario": scenario,
                    }
                )
        self.assertEqual(e.next_event(0), {"kind": "routine"})

    def test_investigation_catalog_entries_are_not_normal_scenarios(self):
        investigation = dict(
            a.workload.SCENARIOS["restart"], lane="investigation", prefer=[]
        )
        with patch.dict(a.workload.SCENARIOS, {"investigate_restart": investigation}):
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertNotIn("investigate_restart", module.SCENARIOS)
            engine = module.Reconciler(FakeKube(), ["demo"], "test")
            self.assertNotIn(
                "investigate_restart", {s["id"] for s in engine.state()["scenarios"]}
            )
            import random

            rng = random.Random(17)
            for _ in range(200):
                self.assertNotEqual(
                    engine.auto_pick([{"name": "checkout-api", "labels": {}}], rng)[1],
                    "investigate_restart",
                )

    def test_triggered_evidence_excludes_noise_preserves_signal(self):
        e = self.noise_engine()
        noise = json.dumps({"event": "routine_heartbeat", "at": 1})
        signal = json.dumps({"event": "checkout_completed", "status": 200})
        e.stimulus(
            {
                "namespace": "jev-label-demo",
                "pod": "checkout-api",
                "scenario": "healthy",
            }
        )
        with patch.object(e.kube, "logs", return_value=[noise, signal, noise]):
            item = e.snapshot(e.next_event(0))[0]
        self.assertEqual(item["candidate"]["pod"]["logs"], [signal])

    def test_workload_emits_real_routine_stdout(self):
        text = (Path(__file__).parent / "simulation/fixtures.yaml").read_text()
        source = text.split("  workload.py: |\n", 1)[1].split("\n---", 1)[0]
        source = "\n".join(line[4:] for line in source.splitlines())
        scope = {"__name__": "test_workload"}
        exec(compile(source, "workload.py", "exec"), scope)
        output = io.StringIO()
        with (
            patch("sys.stdout", output),
            patch.object(scope["time"], "sleep", side_effect=InterruptedError),
        ):
            with self.assertRaises(InterruptedError):
                scope["routine_logs"]()
        event = json.loads(output.getvalue())
        self.assertEqual(event["event"], "routine_heartbeat")
        self.assertGreater(event["at"], 0)

    def test_ordinary_pods_have_routing_choices_without_reference_pods(self):
        for name, scenario, expected in (
            ("checkout-api", "healthy", "stable"),
            ("orders-api", "healthy", "stable"),
            ("analytics-worker", "batch", "batch"),
        ):
            e = self.owned_engine(name)
            e.kube.target["metadata"]["namespace"] = "jev-label-demo"
            e.namespaces = {"jev-label-demo"}
            e.kube.target["metadata"]["annotations"][
                "jev.expanso.io/workload-version"
            ] = "ordinary-v3"
            e.kube.target["metadata"]["labels"] = {"app": name, "team": "payments"}
            with patch.object(e.kube, "pods", side_effect=lambda: [e.kube.target]):
                state = e.state()
                self.assertEqual(len(state["available_labels"]), len(a.ROUTING_LABELS))
                self.assertTrue(state["pods"][0]["event_enabled"])
                e.stimulus(
                    {"namespace": "jev-label-demo", "pod": name, "scenario": scenario}
                )
                item = e.snapshot(e.next_event(0))[0]
                c = item["candidate"]
                self.assertEqual(
                    (c["operation"], c["key"], c["value"]),
                    (
                        "add",
                        "workload" if scenario == "batch" else "health",
                        "batch" if scenario == "batch" else "healthy",
                    ),
                )
                self.assertEqual(c["catalog"]["origin"], "demo configuration")
                e.pending[item["id"]]["score"] = 0.99
                self.assertEqual(e.execute(item["id"])["result"], "applied")
                self.assertEqual(
                    e.kube.target["metadata"]["labels"][c["key"]], c["value"]
                )

    def test_ordinary_catalog_excludes_unlisted_values_and_identity(self):
        target = pod("orders-api", namespace="jev-label-demo")
        target["metadata"]["annotations"] = {
            "jev.expanso.io/fixture": "visual-v1",
            "jev.expanso.io/workload-version": "ordinary-v3",
        }
        source = pod("other", {"team": "rogue", "routing-tier": "canary"})
        options = a.candidates([target, source], {"jev-label-demo"})
        self.assertEqual(
            {(c["key"], c["value"]) for c in options},
            {(c["key"], c["value"]) for c in a.ROUTING_LABELS},
        )

    def test_demo_catalog_does_not_apply_to_unrelated_pods(self):
        target = pod("unrelated", namespace="jev-label-demo")
        target["metadata"]["annotations"]["jev.expanso.io/workload-version"] = (
            "ordinary-v3"
        )
        self.assertEqual(a.candidates([target], {"jev-label-demo"}), [])

    def test_queue_ack_does_not_call_kubernetes_or_model(self):
        e = self.owned_engine()
        with patch.object(e.kube, "get") as get, patch.object(e.kube, "event") as event:
            receipt = e.stimulus(
                {"namespace": "demo", "pod": "checkout-api", "scenario": "healthy"}
            )
            get.assert_not_called()
            event.assert_not_called()
        self.assertEqual(receipt["stage"], "queued")
        self.assertEqual(e.next_event(0)["request_id"], receipt["request_id"])
        self.assertEqual(e.next_event(0), {"kind": "routine"})

    def test_cloud_consumption_collects_correlated_real_logs(self):
        for name in a.FIXTURES:
            e = self.owned_engine(name)
            queued = e.stimulus(
                {"namespace": "demo", "pod": name, "scenario": "healthy"}
            )
            request = e.next_event(0)
            item = e.snapshot(request)[0]
            self.assertEqual(item["candidate"]["request_id"], queued["request_id"])
            self.assertEqual(item["candidate"]["pod"]["name"], name)
            self.assertEqual(
                [x["stage"] for x in e.events], ["queued", "event", "collected"]
            )
            with self.assertRaises(ValueError):
                e.snapshot(request)
            self.assertEqual(e.snapshot({}), [])

    def test_cloud_rechecks_fixture_ownership_before_exec(self):
        e = self.owned_engine()
        e.stimulus({"namespace": "demo", "pod": "checkout-api", "scenario": "egress"})
        e.kube.target["metadata"]["annotations"].clear()
        with patch.object(e.kube, "event") as event, self.assertRaises(ValueError):
            e.snapshot(e.next_event(0))
        event.assert_not_called()

    def test_safe_keys_and_new_event_allow_owned_label_recovery(self):
        p = self.managed()
        undo = a.candidates([p], {"demo"})[0]
        undo["request_id"] = "old"
        p = apply_patch(p, a.patch_for(p, undo, 0.99))
        source = pod(
            "source", {"team": "payments", "pod-template-hash": "bad"}, "other"
        )
        self.assertEqual(a.candidates([p, source], {"demo"}, "old"), [])
        options = a.candidates([p, source], {"demo"}, "new")
        self.assertEqual([c["key"] for c in options], ["team"])
        options[0]["request_id"] = "new"
        updated = apply_patch(p, a.patch_for(p, options[0], 0.99))
        self.assertEqual(updated["metadata"]["labels"]["team"], "payments")

    def test_cursor_feed_and_bounded_queue(self):
        e = self.owned_engine()
        body = {"namespace": "demo", "pod": "checkout-api", "scenario": "batch"}
        for _ in range(32):
            e.stimulus(body)
        with self.assertRaises(a.queue.Full):
            e.stimulus(body)
        feed = e.event_feed(30)
        self.assertEqual([v["seq"] for v in feed["events"]], [31, 32])
        self.assertEqual(feed["cursor"], 32)

    def test_cloud_event_http_path_and_failure_terminal(self):
        e = self.owned_engine()
        server = a.ThreadingHTTPServer(("127.0.0.1", 0), a.handler(e, "test-token"))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()

        def request(method, path, data=None, auth=True):
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            headers = {"Authorization": "Bearer test-token"} if auth else {}
            connection.request(
                method, path, json.dumps(data) if data else None, headers
            )
            response = connection.getresponse()
            payload = response.read()
            connection.close()
            return response.status, json.loads(
                payload
            ) if response.status != 401 else None

        try:
            self.assertEqual(request("POST", "/next-event", auth=False)[0], 401)
            e.stimulus(
                {"namespace": "demo", "pod": "checkout-api", "scenario": "healthy"}
            )
            status, event = request("POST", "/next-event")
            self.assertEqual(status, 200)
            with patch.object(e.kube, "event", side_effect=RuntimeError):
                self.assertEqual(request("POST", "/candidates", event)[0], 503)
            status, feed = request("GET", "/api/events?after=0", auth=False)
            self.assertEqual(status, 200)
            terminal = feed["events"][-1]
            self.assertEqual(terminal["stage"], "error")
            self.assertEqual(terminal["request_id"], event["request_id"])
            self.assertGreaterEqual(terminal["elapsed_ms"], 0)
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_each_event_proposes_its_own_label_on_every_demo_pod(self):
        for name in a.FIXTURES:
            for scenario in a.SCENARIOS:
                with self.subTest(pod=name, scenario=scenario):
                    e = self.noise_engine()
                    e.kube.target["metadata"]["name"] = name
                    e.stimulus(
                        {
                            "namespace": "jev-label-demo",
                            "pod": name,
                            "scenario": scenario,
                        }
                    )
                    item = e.snapshot(e.next_event(0))[0]
                    c = item["candidate"]
                    self.assertEqual(
                        [c["operation"], c["key"], c["value"]],
                        a.workload.SCENARIOS[scenario]["prefer"][0],
                    )
                    e.pending[item["id"]]["score"] = 0.99
                    self.assertEqual(e.execute(item["id"])["result"], "applied")

    def test_event_question_preserves_evidence_without_old_label_votes(self):
        e = self.noise_engine()
        e.stimulus(
            {
                "namespace": "jev-label-demo",
                "pod": "checkout-api",
                "scenario": "healthy",
            }
        )
        c = e.snapshot(e.next_event(0))[0]["candidate"]
        c["pod"]["labels"]["health"] = "degraded"
        state = a.question(c)["state"]
        self.assertEqual(state["latest_event"], c["trigger"])
        self.assertEqual(state["recent_logs"], c["pod"]["logs"])
        self.assertEqual(state["label"]["value"], "healthy")
        self.assertNotIn("pod", state)
        self.assertEqual(c["pod"]["labels"]["health"], "degraded")

    def test_explicit_event_refresh_and_recovery_require_owned_label(self):
        e = self.noise_engine()
        requests = []
        for scenario, value in [
            ("crashloop", "degraded"),
            ("crashloop", "degraded"),
            ("healthy", "healthy"),
        ]:
            e.stimulus(
                {
                    "namespace": "jev-label-demo",
                    "pod": "checkout-api",
                    "scenario": scenario,
                }
            )
            item = e.snapshot(e.next_event(0))[0]
            c = item["candidate"]
            requests.append(c["request_id"])
            self.assertEqual(
                (c["operation"], c["key"], c["value"]), ("add", "health", value)
            )
            e.pending[item["id"]]["score"] = 0.99
            self.assertEqual(e.execute(item["id"])["result"], "applied")
            self.assertEqual(
                a.ledger(e.kube.target)["health"]["request_id"], requests[-1]
            )
        self.assertEqual(len(e.kube.patches), 3)
        p = e.kube.target
        self.assertFalse(a.can_refresh(p, "health", "healthy", requests[-1]))
        self.assertFalse(a.can_refresh(p, "health", "healthy", None))
        self.assertFalse(a.can_refresh(p, "health", "invented", "new"))
        self.assertFalse(
            any(
                c["operation"] == "add" and c["key"] == "health"
                for c in a.candidates([p], e.namespaces)
            )
        )
        for request_id in (requests[-1], None):
            c = {
                "operation": "add",
                "key": "health",
                "value": "healthy",
                "request_id": request_id,
                "pod": a.view(p),
            }
            with self.subTest(request_id=request_id), self.assertRaises(ValueError):
                a.patch_for(p, c, 0.99)
        for mutation in ("edited", "unowned", "nonfixture", "withdrawn"):
            changed = copy.deepcopy(p)
            if mutation == "edited":
                changed["metadata"]["labels"]["health"] = "external"
            elif mutation == "unowned":
                del changed["metadata"]["annotations"][a.LEDGER]
            elif mutation == "nonfixture":
                del changed["metadata"]["annotations"]["jev.expanso.io/fixture"]
            else:
                journal = a.ledger(changed)
                journal["health"]["state"] = "withdrawn"
                changed["metadata"]["annotations"][a.LEDGER] = json.dumps(journal)
            c = {
                "operation": "add",
                "key": "health",
                "value": "healthy",
                "request_id": "new",
                "pod": a.view(changed),
            }
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                a.patch_for(changed, c, 0.99)
        e.stimulus(
            {
                "namespace": "jev-label-demo",
                "pod": "checkout-api",
                "scenario": "healthy",
            }
        )
        item = e.snapshot(e.next_event(0))[0]
        e.pending[item["id"]]["score"] = 0.1
        self.assertEqual(e.execute(item["id"])["result"], "held")
        self.assertEqual(len(e.kube.patches), 3)

    def test_squeeze_adds_cpu_label_despite_existing_health(self):
        e = self.noise_engine()
        e.kube.target["metadata"]["labels"].update(
            {"health": "degraded", "routing-tier": "batch"}
        )
        e.stimulus(
            {
                "namespace": "jev-label-demo",
                "pod": "checkout-api",
                "scenario": "squeeze",
            }
        )
        item = e.snapshot(e.next_event(0))[0]
        self.assertEqual(
            (
                item["candidate"]["operation"],
                item["candidate"]["key"],
                item["candidate"]["value"],
            ),
            ("add", "cpu", "throttled"),
        )
        e.pending[item["id"]]["score"] = 0.99
        self.assertEqual(e.execute(item["id"])["result"], "applied")
        self.assertEqual(e.kube.target["metadata"]["labels"]["cpu"], "throttled")

    def test_owned_fixture_existing_labels_get_nonmutating_review(self):
        for score in (0.01, 0.99):
            e = self.owned_engine("orders-api")
            e.kube.target["metadata"]["labels"] = {
                "team": "payments",
                "routing-tier": "stable",
            }
            initial = copy.deepcopy(e.kube.target)
            queued = e.stimulus(
                {
                    "namespace": "demo",
                    "pod": "orders-api",
                    "scenario": "probe",
                }
            )
            item = e.snapshot(e.next_event(0))[0]
            candidate = item["candidate"]
            self.assertEqual(candidate["operation"], "review")
            self.assertEqual(candidate["key"], "routing-tier")
            self.assertEqual(candidate["request_id"], queued["request_id"])
            prompt = a.question(candidate)["questions"]["act"]["instructions"]
            self.assertIn("accurately describe this pod NOW", prompt)
            self.assertIn("read-only review", prompt)
            response = io.BytesIO(
                json.dumps({"answers": {"act": {"noul": score}}}).encode()
            )
            with patch.object(
                a.urllib.request, "urlopen", return_value=response
            ) as model:
                e.judge(item["id"])
                model.assert_called_once()
            receipt = e.execute(item["id"])
            self.assertEqual(receipt["result"], "held")
            self.assertIn("ownership is protected", receipt["message"])
            self.assertEqual(e.kube.patches, [])
            self.assertEqual(e.kube.target["metadata"], initial["metadata"])
            terminal = e.events[-1]
            self.assertEqual(terminal["request_id"], queued["request_id"])
            self.assertTrue(terminal["model_called"])
            self.assertEqual(
                [x["stage"] for x in e.events],
                ["queued", "event", "collected", "judging", "judged", "held"],
            )

    def test_no_safe_existing_label_still_skips_model(self):
        e = self.owned_engine()
        e.kube.target["metadata"]["labels"] = {"app": "checkout"}
        e.stimulus({"namespace": "demo", "pod": "checkout-api", "scenario": "probe"})
        with patch.object(e.kube, "pods", return_value=[e.kube.target]):
            self.assertEqual(e.snapshot(e.next_event(0)), [])
        self.assertFalse(e.events[-1]["model_called"])
        self.assertEqual(e.events[-1]["stage"], "held")

    def test_fixture_waits_for_logs_and_exposes_click_eligibility(self):
        e = self.engine()
        e.kube.target = pod("checkout-api")
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/fixture"] = "visual-v1"
        with patch.object(e.kube, "logs", return_value=[]):
            self.assertEqual(e.snapshot(), [])
        self.assertTrue(e.state()["pods"][0]["event_enabled"])
        self.assertTrue(e.snapshot())
        e.kube.target["metadata"]["name"] = "orders-api"
        self.assertTrue(e.state()["pods"][0]["event_enabled"])

    def test_successful_mutation_releases_selected_focus(self):
        e = self.engine()
        e.selected = ("demo", "target")
        e.execute(self.decision(e))
        self.assertIsNone(e.selected)

    def test_state_does_not_need_mutation_lock(self):
        e = self.engine()
        server = a.ThreadingHTTPServer(("127.0.0.1", 0), a.handler(e, "secret"))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        e.lock.acquire()
        try:
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            connection.close()
        finally:
            e.lock.release()
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_cloud_requires_matching_current_running_execution_and_caches(self):
        from unittest.mock import Mock

        node = "00000000-0000-0000-0000-000000000001"
        connection = Mock()
        connection.read_text.return_value = "node_id: " + node
        job = {
            "id": "j-demo",
            "status": {"version": 2, "state": {"state_type": "running"}},
        }
        execution = {
            "id": "e-demo",
            "job_id": "j-demo",
            "job_version": 2,
            "node_id": node,
            "namespace": "demo",
            "status": {
                "desired_state": {"state_type": "running"},
                "observed_state": {"state_type": "running"},
            },
        }
        with patch.dict(
            a.os.environ,
            {
                "EXPANSO_CLI_ENDPOINT": "https://example.invalid",
                "EXPANSO_CLI_AUTH_API_KEY": "fake",
            },
        ):
            for change in (
                {},
                {"job_version": 1},
                {"node_id": "wrong"},
                {"job_id": "wrong"},
            ):
                cloud = a.CloudStatus(connection)
                with patch.object(
                    cloud, "command", side_effect=[job, [dict(execution, **change)]]
                ) as command:
                    result = cloud.read()
                    self.assertEqual(
                        result["state"], "unknown" if change else "running"
                    )
                    self.assertEqual(result, cloud.read())
                    self.assertEqual(command.call_count, 2)
        cloud = a.CloudStatus(connection)
        with (
            patch.dict(a.os.environ, {}, clear=True),
            patch.object(cloud, "command") as command,
        ):
            self.assertEqual(cloud.read()["state"], "unknown")
            command.assert_not_called()

    def test_logs_feed_inference(self):
        e = self.engine()
        item = e.snapshot()[0]
        self.assertIn(
            "checkout_completed",
            a.question(item["candidate"])["state"]["pod"]["logs"][0],
        )
        self.assertEqual(e.state()["cloud"]["state"], "unknown")
        self.assertIsNotNone(e.state()["cloud"]["last_tick_at"])

    def test_stimulus_only_emits_workload_event_and_invalidates(self):
        e = self.engine()
        e.kube.target = pod("checkout-api")
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/fixture"] = "visual-v1"
        token = self.decision(e)
        with patch.object(a.urllib.request, "urlopen") as model:
            result = e.stimulus(
                {"namespace": "demo", "pod": "checkout-api", "scenario": "healthy"}
            )
        self.assertEqual(result["stage"], "queued")
        self.assertEqual(e.kube.patches, [])
        model.assert_not_called()
        with self.assertRaises(ValueError):
            e.entry(token)

    def test_stimulus_rejects_unowned_or_malformed_target(self):
        e = self.engine()
        for body in [
            None,
            [],
            {},
            {"namespace": "demo", "pod": "--help", "scenario": "probe"},
            {"namespace": "demo", "pod": "checkout-api", "scenario": "shell"},
        ]:
            with self.subTest(body=body), self.assertRaises((ValueError, TypeError)):
                e.stimulus(body)
        self.assertEqual(e.kube.patches, [])

    def test_ui_http_boundaries(self):
        e = self.engine()
        e.kube.target = pod("checkout-api")
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/fixture"] = "visual-v1"
        server = a.HTTPServer(("127.0.0.1", 0), a.handler(e, "cloud-secret"))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()

        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            data = response.read()
            connection.close()
            return response.status, data

        try:
            for asset, signature in (
                ("expanso-logo-full-violet.svg", b"<svg"),
                ("typesafe-mark.png", b"\x89PNG"),
            ):
                status, payload = request("GET", "/assets/" + asset)
                self.assertEqual(status, 200)
                self.assertTrue(payload.startswith(signature))
            self.assertEqual(request("GET", "/assets/../../.env")[0], 404)
            status, payload = request("GET", "/api/session")
            self.assertEqual(status, 200)
            self.assertNotIn(b"cloud-secret", payload)
            csrf = json.loads(payload)["csrf_token"]
            origin = "http://127.0.0.1:" + str(server.server_port)
            body = json.dumps(
                {"namespace": "demo", "pod": "checkout-api", "scenario": "healthy"}
            )
            for headers in [
                {},
                {"Origin": origin},
                {"Origin": "https://evil.example", "X-CSRF-Token": csrf},
                {
                    "Host": "evil.example",
                    "Origin": "http://evil.example",
                    "X-CSRF-Token": csrf,
                },
            ]:
                self.assertEqual(request("POST", "/api/event", body, headers)[0], 403)
            headers = {"Origin": origin, "X-CSRF-Token": csrf}
            self.assertEqual(request("POST", "/api/event", body, headers)[0], 202)
            self.assertEqual(request("POST", "/api/event", "[]", headers)[0], 400)
            self.assertEqual(
                request("GET", "/api/state", headers={"Host": "evil.example"})[0], 403
            )
            self.assertEqual(request("GET", "/../../.env")[0], 404)
            self.assertEqual(request("POST", "/judge", "{}", headers)[0], 401)
            self.assertEqual(e.kube.patches, [])
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_inventory_reads_other_namespaces(self):
        self.assertEqual(candidate()["sources"][0]["namespace"], "other")

    def test_only_explicit_target_namespaces(self):
        self.assertEqual(a.candidates([pod()], {"elsewhere"}), [])

    def test_preserves_existing_label_value(self):
        self.assertEqual(
            a.candidates(
                [
                    pod(labels={"team": "data"}),
                    pod("source", {"team": "payments"}, "other"),
                ],
                {"demo"},
            ),
            [],
        )

    def test_atomic_journal_and_label(self):
        p = pod()
        operations = a.patch_for(p, candidate(p), 0.99)
        self.assertEqual(
            [op["op"] for op in operations], ["test", "test", "add", "add"]
        )
        updated = apply_patch(p, operations)
        self.assertEqual(updated["metadata"]["labels"]["team"], "payments")
        self.assertEqual(a.ledger(updated)["team"]["previous"], None)

    def test_stale_resource_version_rejected(self):
        p = pod()
        c = candidate(p)
        p["metadata"]["resourceVersion"] = "9"
        with self.assertRaises(ValueError):
            a.patch_for(p, c, 0.99)

    def test_recreated_pod_rejected(self):
        p = pod()
        c = candidate(p)
        p["metadata"]["uid"] = "new-uid"
        with self.assertRaises(ValueError):
            a.patch_for(p, c, 0.99)

    def test_signal_changes_judgment_context(self):
        p = pod()
        p["metadata"]["annotations"][a.SIGNAL] = "policy denied stable traffic"
        self.assertEqual(candidate(p)["pod"]["signal"], "policy denied stable traffic")

    def managed(self):
        p = pod()
        return apply_patch(p, a.patch_for(p, candidate(p), 0.99))

    def test_undo_survives_adapter_restart(self):
        p = self.managed()
        c = a.candidates([p], {"demo"})[0]
        self.assertEqual(c["operation"], "undo")
        updated = apply_patch(p, a.patch_for(p, c, 0.98))
        self.assertNotIn("team", updated["metadata"]["labels"])
        self.assertEqual(a.ledger(updated)["team"]["state"], "withdrawn")

    def test_undo_preserves_external_edit(self):
        p = self.managed()
        p["metadata"]["labels"]["team"] = "security"
        c = a.candidates([p], {"demo"})[0]
        with self.assertRaises(ValueError):
            a.patch_for(p, c, 0.99)

    def test_undo_cannot_remove_unowned_labels(self):
        p = pod(labels={"team": "payments"})
        c = {"operation": "undo", "key": "team", "value": "payments", "pod": a.view(p)}
        with self.assertRaises(ValueError):
            a.patch_for(p, c, 0.99)

    def test_withdrawn_label_not_readded(self):
        p = self.managed()
        undo = a.candidates([p], {"demo"})[0]
        p = apply_patch(p, a.patch_for(p, undo, 0.99))
        self.assertEqual(
            a.candidates([p, pod("source", {"team": "payments"}, "other")], {"demo"}),
            [],
        )

    def test_invalid_model_answers_rejected(self):
        for value in [None, "0.99", True, -1, 2, float("nan"), float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                a.probability({"answers": {"act": {"noul": value}}})

    def engine(self, apply=True):
        return a.Reconciler(FakeKube(), {"demo"}, "test-only", apply=apply)

    def decision(self, engine, score=0.99):
        token = engine.snapshot()[0]["id"]
        engine.pending[token]["score"] = score
        return token

    def test_apply_requires_server_verified_judgment(self):
        e = self.engine()
        token = e.snapshot()[0]["id"]
        with self.assertRaises(ValueError):
            e.execute(token)
        self.assertEqual(e.kube.patches, [])

    def test_low_probability_holds(self):
        e = self.engine()
        self.assertEqual(e.execute(self.decision(e, 0.51))["result"], "held")
        self.assertEqual(e.kube.patches, [])

    def test_dry_run_never_patches(self):
        e = self.engine(False)
        self.assertEqual(e.execute(self.decision(e))["result"], "dry-run")
        self.assertEqual(e.kube.patches, [])

    def test_apply_receipt_and_repeat_rejected(self):
        e = self.engine()
        token = self.decision(e)
        self.assertEqual(e.execute(token)["result"], "applied")
        with self.assertRaises(ValueError):
            e.execute(token)
        self.assertEqual(len(e.kube.patches), 1)

    def test_expired_candidate_rejected(self):
        e = self.engine()
        token = self.decision(e)
        e.pending[token]["expires"] = 0
        with self.assertRaises(ValueError):
            e.execute(token)

    def test_jev_outage_cannot_apply(self):
        e = self.engine()
        token = e.snapshot()[0]["id"]
        with patch.object(a.urllib.request, "urlopen", side_effect=OSError):
            with self.assertRaises(OSError):
                e.judge(token)
        with self.assertRaises(ValueError):
            e.execute(token)
        self.assertEqual(e.kube.patches, [])

    def test_bad_journal_does_not_disable_other_pods(self):
        for broken in ["bad-json", "[]", '{"team": {}}']:
            with self.subTest(broken=broken):
                p = pod("broken")
                p["metadata"]["annotations"][a.LEDGER] = broken
                with patch.object(a.sys, "stderr", io.StringIO()) as errors:
                    items = a.candidates(
                        [p, pod(), pod("source", {"team": "payments"}, "other")],
                        {"demo"},
                    )
                    self.assertEqual([x["pod"]["name"] for x in items], ["target"])
                    self.assertIn("quarantined", errors.getvalue())

    def test_single_candidate_per_tick_and_fair_rotation(self):
        e = self.engine()
        with patch.object(
            e.kube,
            "pods",
            return_value=[
                pod(),
                pod("source", {"team": "payments", "routing-tier": "stable"}, "other"),
            ],
        ):
            first = e.snapshot()
            second = e.snapshot()
            third = e.snapshot()
            self.assertEqual(len(first), 1)
            self.assertNotEqual(
                first[0]["candidate"]["key"], second[0]["candidate"]["key"]
            )
            self.assertEqual(first[0]["candidate"]["key"], third[0]["candidate"]["key"])

    def test_failed_rejudgment_clears_prior_score(self):
        e = self.engine()
        token = self.decision(e)
        with patch.object(a.urllib.request, "urlopen", side_effect=OSError):
            with self.assertRaises(OSError):
                e.judge(token)
        with self.assertRaises(ValueError):
            e.execute(token)

    def test_authenticated_http_roundtrip_and_undo(self):
        e = self.engine()
        server = a.HTTPServer(("127.0.0.1", 0), a.handler(e, "test-token"))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()

        def post(path, data, authorized=True):
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            headers = {"Authorization": "Bearer test-token"} if authorized else {}
            connection.request("POST", path, json.dumps(data), headers)
            response = connection.getresponse()
            payload = response.read()
            connection.close()
            return response.status, json.loads(
                payload
            ) if response.status != 401 else None

        try:
            self.assertEqual(post("/candidates", {}, False)[0], 401)
            for expected in ["applied", "undone"]:
                options = e.snapshot()
                status = 200
                self.assertEqual(status, 200)
                token = options[0]["id"]
                # Forging a model answer in the request cannot authorize a write.
                self.assertEqual(post("/apply", {"id": token, "noul": 1})[0], 503)
                answer = io.BytesIO(b'{"answers":{"act":{"noul":0.99}}}')
                with patch.object(a.urllib.request, "urlopen", return_value=answer):
                    self.assertEqual(post("/judge", {"id": token})[0], 200)
                self.assertEqual(post("/apply", {"id": token})[1]["result"], expected)
            self.assertNotIn("team", e.kube.target["metadata"]["labels"])
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_deploy_rejects_missing_multiple_and_disconnected_nodes(self):
        module_spec = importlib.util.spec_from_file_location(
            "deploy", Path(__file__).with_name("deploy.py")
        )
        deploy = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(deploy)
        node = {"id": "expected", "status": {"connection_state": "connected"}}
        self.assertEqual(deploy.selected_node([node]), "expected")
        for nodes in [
            [],
            [node, node],
            [{"id": "other", "status": {"connection_state": "disconnected"}}],
        ]:
            with self.assertRaises(ValueError):
                deploy.selected_node(nodes)


class SignalCatalogTests(unittest.TestCase):
    def test_fixture_embeds_the_workload_verbatim(self):
        import pathlib
        import textwrap

        here = pathlib.Path(__file__).parent
        source = (here / "simulation/workload.py").read_text()
        fixture = (here / "simulation/fixtures.yaml").read_text()
        start = fixture.index("  workload.py: |\n") + len("  workload.py: |\n")
        embedded = textwrap.dedent(
            fixture[start : fixture.index("\n---\n", start)] + "\n"
        )
        self.assertEqual(embedded.strip(), source.strip())

    def test_every_scenario_only_proposes_catalog_labels(self):
        catalog = {(c["key"], c["value"]) for c in a.ROUTING_LABELS}
        for name, spec in a.workload.SCENARIOS.items():
            self.assertTrue(spec["title"] and spec["why"] and spec["message"], name)
            for op, key, value in spec["prefer"]:
                self.assertIn(op, {"add", "undo"}, name)
                self.assertIn((key, value), catalog, name)

    def test_auto_pick_visits_all_classifications_and_skips_busy_pods(self):
        import random

        e = a.Reconciler.__new__(a.Reconciler)
        rng = random.Random(7)
        loaded = {
            "name": "checkout-api",
            "labels": {"health": "healthy", "traffic": "drain"},
        }
        self.assertIsNone(e.auto_pick([dict(loaded, busy=True)], rng))
        seen = {e.auto_pick([loaded], rng)[1] for _ in range(300)}
        self.assertEqual(seen, a.SCENARIOS)


if __name__ == "__main__":
    unittest.main()
