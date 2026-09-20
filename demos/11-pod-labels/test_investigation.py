"""Contract tests for Cloud-driven evidence gating and diagnosis."""

import unittest
from unittest.mock import patch
from test_adapter import a, FakeKube, pod
import investigation as inv


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.k = FakeKube()
        self.k.target = pod("checkout-api", namespace="demo")
        self.k.target["metadata"]["annotations"]["jev.expanso.io/fixture"] = "visual-v1"
        self.r = a.Reconciler(self.k, {"demo"}, "test")

    def collect(self, phase="restart"):
        self.r.investigation_request(
            {"namespace": "demo", "pod": "checkout-api", "phase": phase}
        )
        return self.r.snapshot(self.r.next_event())[0]["id"]

    def test_waiting(self):
        token = self.collect()
        self.r.pending[token]["score"] = 0.4
        self.assertEqual(self.r.execute(token)["stage"], "investigation_waiting")

    def test_ready_without_another_provider(self):
        token = self.collect()
        self.r.pending[token]["score"] = 0.98
        with patch("subprocess.run", side_effect=AssertionError("No provider")):
            result = self.r.execute(token)
        self.assertEqual(result["stage"], "investigation_ready")
        self.assertEqual(result["investigation"]["status"], "ready")
        self.assertNotIn("diagnosis", result["investigation"])
        with self.assertRaises(ValueError):
            self.r.execute(token)

    def test_stale_uid(self):
        token = self.collect()
        self.r.pending[token]["score"] = 0.99
        self.k.target["metadata"]["uid"] = "changed"
        with self.assertRaises(ValueError):
            self.r.execute(token)

    def test_superseded_phase(self):
        token = self.collect()
        self.collect("context")
        self.r.pending[token]["score"] = 0.99
        with self.assertRaises(ValueError):
            self.r.execute(token)

    def test_scope_and_ownership(self):
        for body in [
            {"namespace": "other", "pod": "checkout-api", "phase": "restart"},
            {"namespace": "demo", "pod": "source", "phase": "restart"},
        ]:
            with self.assertRaises(ValueError):
                self.r.investigation_request(body)
        self.k.target["metadata"]["annotations"] = {}
        with self.assertRaises(ValueError):
            self.collect()

    def test_question_is_sufficiency(self):
        instructions = inv.question({})["questions"]["act"]["instructions"]
        self.assertIn("sufficiency, not severity", instructions)


if __name__ == "__main__":
    unittest.main()
