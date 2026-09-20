import unittest
from unittest.mock import Mock

from routing import membership


class RoutingTests(unittest.TestCase):
    def test_only_ready_real_endpoints_count(self):
        kube = Mock()
        kube.run.side_effect = [
            {"spec": {"selector": {"app": "checkout", "routing-tier": "stable"}}},
            {
                "items": [
                    {
                        "endpoints": [
                            {
                                "conditions": {"ready": True},
                                "addresses": ["10.0.0.1"],
                                "targetRef": {"kind": "Pod", "name": "checkout-api"},
                            },
                            {
                                "conditions": {"ready": False},
                                "addresses": ["10.0.0.2"],
                                "targetRef": {"kind": "Pod", "name": "orders-api"},
                            },
                            {
                                "conditions": {},
                                "addresses": ["10.0.0.3"],
                                "targetRef": {
                                    "kind": "Pod",
                                    "name": "analytics-worker",
                                },
                            },
                        ]
                    }
                ]
            },
        ]
        self.assertEqual(membership(kube)["pods"], ["checkout-api"])

    def test_null_endpoints_are_an_observed_empty_service(self):
        kube = Mock()
        kube.run.side_effect = [{"spec": {}}, {"items": [{"endpoints": None}]}]
        self.assertEqual(membership(kube)["state"], "observed")

    def test_error_is_unknown_not_empty_membership(self):
        kube = Mock()
        kube.run.side_effect = RuntimeError("provider detail")
        self.assertEqual(membership(kube)["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
