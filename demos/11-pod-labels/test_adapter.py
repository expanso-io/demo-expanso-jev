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
            "noise-v4"
        )
        return e

    def test_cloud_routine_reads_once_without_judgment_or_mutation(self):
        e = self.noise_engine()
        line = json.dumps({"event": "routine_heartbeat", "at": 1})
        with patch.object(e.kube, "logs", return_value=[line]) as logs:
            with patch.object(e, "judge") as judge:
                self.assertEqual(e.snapshot(e.next_event(0)), [])
                self.assertEqual(e.events[-1]["stage"], "routine")
                self.assertEqual(e.events[-1]["count"], 1)
                self.assertEqual(e.events[-1]["logs"], [line])
                self.assertEqual(e.snapshot(e.next_event(0)), [])
                self.assertEqual(len(e.events), 1)
                judge.assert_not_called()
            self.assertEqual(logs.call_count, 2)
        self.assertEqual(e.pending, {})
        self.assertEqual(e.kube.patches, [])

    def test_routine_collection_requires_recognized_owned_fixture(self):
        e = self.noise_engine()
        e.kube.target["metadata"]["annotations"].clear()
        with patch.object(e.kube, "logs") as logs:
            self.assertEqual(e.collect_routine(), [])
            logs.assert_not_called()
        self.assertEqual(e.events, [])

    def test_triggered_evidence_excludes_noise_preserves_signal(self):
        e = self.noise_engine()
        noise = json.dumps({"event": "routine_heartbeat", "at": 1})
        signal = json.dumps({"event": "checkout_completed", "status": 200})
        e.stimulus(
            {
                "namespace": "jev-label-demo",
                "pod": "checkout-api",
                "scenario": "checkout",
            }
        )
        with patch.object(e.kube, "logs", return_value=[noise, signal, noise]):
            item = e.snapshot(e.next_event(0))[0]
        self.assertEqual(item["candidate"]["pod"]["logs"], [signal])

    def test_workload_emits_real_routine_stdout(self):
        text = Path(__file__).with_name("fixtures.yaml").read_text()
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
            ("checkout-api", "checkout", "stable"),
            ("orders-api", "recovery", "stable"),
            ("analytics-worker", "analytics", "batch"),
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
                self.assertEqual(len(state["available_labels"]), 2)
                self.assertTrue(state["pods"][0]["event_enabled"])
                e.stimulus(
                    {"namespace": "jev-label-demo", "pod": name, "scenario": scenario}
                )
                item = e.snapshot(e.next_event(0))[0]
                c = item["candidate"]
                self.assertEqual(
                    (c["operation"], c["key"], c["value"]),
                    ("add", "routing-tier", expected),
                )
                self.assertEqual(c["catalog"]["origin"], "demo configuration")
                e.pending[item["id"]]["score"] = 0.99
                self.assertEqual(e.execute(item["id"])["result"], "applied")
                self.assertEqual(
                    e.kube.target["metadata"]["labels"]["routing-tier"], expected
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
            {("routing-tier", "stable"), ("routing-tier", "batch")},
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
                {"namespace": "demo", "pod": "checkout-api", "scenario": "recovery"}
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
                {"namespace": "demo", "pod": name, "scenario": "checkout"}
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
        e.stimulus({"namespace": "demo", "pod": "checkout-api", "scenario": "security"})
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
        body = {"namespace": "demo", "pod": "checkout-api", "scenario": "analytics"}
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
                {"namespace": "demo", "pod": "checkout-api", "scenario": "checkout"}
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
                    "scenario": "failure",
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
        e.stimulus({"namespace": "demo", "pod": "checkout-api", "scenario": "failure"})
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
                {"namespace": "demo", "pod": "checkout-api", "scenario": "checkout"}
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
            {"namespace": "demo", "pod": "--help", "scenario": "failure"},
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
                {"namespace": "demo", "pod": "checkout-api", "scenario": "checkout"}
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


if __name__ == "__main__":
    unittest.main()
