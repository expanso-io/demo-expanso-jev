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

    def test_fixture_waits_for_logs_and_exposes_click_eligibility(self):
        e = self.engine()
        e.kube.target = pod("checkout-new")
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/fixture"] = "visual-v1"
        with patch.object(e.kube, "logs", return_value=[]):
            self.assertEqual(e.snapshot(), [])
        self.assertTrue(e.state()["pods"][0]["event_enabled"])
        self.assertTrue(e.snapshot())
        e.kube.target["metadata"]["name"] = "checkout-reference"
        self.assertFalse(e.state()["pods"][0]["event_enabled"])

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
        e.kube.target = pod("checkout-new")
        e.kube.target["metadata"]["annotations"]["jev.expanso.io/fixture"] = "visual-v1"
        token = self.decision(e)
        with patch.object(a.urllib.request, "urlopen") as model:
            result = e.stimulus(
                {"namespace": "demo", "pod": "checkout-new", "scenario": "checkout"}
            )
        self.assertEqual(result["stage"], "event")
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
            {"namespace": "demo", "pod": "checkout-new", "scenario": "checkout"},
            {"namespace": "demo", "pod": "--help", "scenario": "failure"},
            {"namespace": "demo", "pod": "checkout-new", "scenario": "shell"},
        ]:
            with self.subTest(body=body), self.assertRaises((ValueError, TypeError)):
                e.stimulus(body)
        self.assertEqual(e.kube.patches, [])

    def test_ui_http_boundaries(self):
        e = self.engine()
        e.kube.target = pod("checkout-new")
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
            status, payload = request("GET", "/api/session")
            self.assertEqual(status, 200)
            self.assertNotIn(b"cloud-secret", payload)
            csrf = json.loads(payload)["csrf_token"]
            origin = "http://127.0.0.1:" + str(server.server_port)
            body = json.dumps(
                {"namespace": "demo", "pod": "checkout-new", "scenario": "checkout"}
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
            self.assertEqual(request("POST", "/api/event", body, headers)[0], 200)
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
                pod("source", {"team": "payments", "tier": "web"}, "other"),
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
                status, options = post("/candidates", {})
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
