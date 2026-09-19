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

    def pods(self):
        return [self.target, pod("source", {"team": "payments"}, "other")]

    def get(self, namespace, name):
        return copy.deepcopy(self.target)

    def patch(self, namespace, name, operations):
        self.patches.append(operations)
        self.target = apply_patch(self.target, operations)
        return self.target


class Tests(unittest.TestCase):
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
