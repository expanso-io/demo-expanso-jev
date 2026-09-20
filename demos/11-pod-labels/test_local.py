"""Launcher regression tests; no runtime, cluster or Cloud required."""

import contextlib
import io
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent


class LauncherTests(unittest.TestCase):
    def test_subdirectory_up_selects_pod_launcher(self):
        result = subprocess.run(
            ["just", "--dry-run", "up"],
            cwd=HERE,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertNotIn("01-log-triage", result.stderr)
        self.assertIn("local.py", result.stderr)

    def load(self):
        spec = importlib.util.spec_from_file_location("local", HERE / "local.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_private_config_is_stable_and_scoped(self):
        module = self.load()
        scratch = HERE / ".test-scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            with patch.dict(os.environ, {"KUBE_CONTEXT": "unrelated"}, clear=True):
                first = module.environment(Path(tmp))
                second = module.environment(Path(tmp))
            self.assertEqual(first["POD_LABEL_TOKEN"], second["POD_LABEL_TOKEN"])
            self.assertGreaterEqual(len(first["POD_LABEL_TOKEN"]), 32)
            self.assertEqual(first["KUBE_CONTEXT"], "jev-label-demo")
            self.assertEqual(first["POD_LABEL_NAMESPACES"], "jev-label-demo")
            self.assertEqual(first["POD_LABEL_APPLY"], "true")
            self.assertEqual((Path(tmp) / "local-token").stat().st_mode & 0o777, 0o600)

    def test_cleanup_survives_child_exit_race(self):
        module = self.load()
        session = module.Session.__new__(module.Session)
        session.cloud_job = None
        session.deployment_attempted = False
        session.cluster_started = True
        session.docker_started = False
        session.logs = []
        child = Mock(pid=123)
        child.poll.return_value = None
        session.children = [("adapter", child)]
        session.run = Mock(return_value="")
        with patch.object(module.os, "killpg", side_effect=ProcessLookupError):
            session.close()
        session.run.assert_called_once_with("k3d", "cluster", "stop", module.CLUSTER)

    def test_does_not_stop_replaced_cloud_job(self):
        module = self.load()
        session = module.Session.__new__(module.Session)
        session.cloud_job = ("our-job", 1)
        session.deployment_attempted = True
        session.cluster_started = False
        session.docker_started = False
        session.logs = []
        session.children = []
        session.job = Mock(return_value={"id": "our-job", "status": {"version": 2}})
        session.run = Mock()
        with contextlib.redirect_stderr(io.StringIO()):
            session.close()
        session.run.assert_not_called()

    def test_ambiguous_submission_cleans_local_resources_and_reports(self):
        module = self.load()
        session = module.Session.__new__(module.Session)
        session.cloud_job = None
        session.deployment_attempted = True
        session.cluster_started = True
        session.docker_started = False
        session.children = []
        session.logs = []
        session.run = Mock(return_value="")
        with self.assertRaisesRegex(
            RuntimeError, "Cloud submission outcome is unverified"
        ):
            session.close()
        session.run.assert_called_once_with("k3d", "cluster", "stop", module.CLUSTER)

    def test_fixture_upgrade_preserves_current_and_unrelated_pods(self):
        module = self.load()
        old = {
            "metadata": {
                "name": "checkout-new",
                "namespace": module.CLUSTER,
                "annotations": {"jev.expanso.io/fixture": "visual-v1"},
            },
            "spec": {"containers": []},
        }
        self.assertEqual(module.fixture_upgrade_targets([old]), ["checkout-new"])
        old["metadata"]["annotations"]["jev.expanso.io/workload-version"] = "events-v2"
        self.assertEqual(module.fixture_upgrade_targets([old]), ["checkout-new"])
        old["metadata"]["name"] = "checkout-api"
        old["metadata"]["annotations"]["jev.expanso.io/workload-version"] = (
            "ordinary-v3"
        )
        self.assertEqual(module.fixture_upgrade_targets([old]), [])
        old["metadata"]["annotations"] = {}
        with self.assertRaisesRegex(RuntimeError, "unrecognized"):
            module.fixture_upgrade_targets([old])
        old["metadata"]["namespace"] = "production"
        self.assertEqual(module.fixture_upgrade_targets([old]), [])

    def test_migration_removes_all_owned_old_names_but_preserves_current(self):
        module = self.load()
        import copy

        old = {
            "metadata": {
                "namespace": module.CLUSTER,
                "annotations": {
                    "jev.expanso.io/fixture": "visual-v1",
                    "jev.expanso.io/workload-version": "events-v2",
                },
            },
            "spec": {"containers": []},
        }
        pods = []
        names = ["checkout-new", "checkout-reference", "analytics-reference"]
        for name in names:
            p = copy.deepcopy(old)
            p["metadata"]["name"] = name
            pods.append(p)
        self.assertEqual(module.fixture_upgrade_targets(pods), names)
        for name in ["checkout-api", "orders-api", "analytics-worker"]:
            p = copy.deepcopy(old)
            p["metadata"]["name"] = name
            p["metadata"]["annotations"]["jev.expanso.io/workload-version"] = (
                "ordinary-v3"
            )
            self.assertEqual(module.fixture_upgrade_targets([p]), [])
            del p["metadata"]["annotations"]["jev.expanso.io/fixture"]
            with self.assertRaisesRegex(RuntimeError, "unrecognized"):
                module.fixture_upgrade_targets([p])

    def test_port_collision_fails_before_starting_services(self):
        module = self.load()
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                module.require_free_port(sock.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
