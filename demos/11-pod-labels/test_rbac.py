# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Offline checks on rbac/rbac.yaml. No cluster; rbac/verify.py is the live one.

The grants must be exactly what the adapter's kubectl calls need and nothing
wider, and they must change when the adapter's calls change.
"""

import ast
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DOCS = list(yaml.safe_load_all((HERE / "rbac/rbac.yaml").read_text()))


def grants(kind):
    out = set()
    for doc in DOCS:
        if doc["kind"] != kind:
            continue
        for rule in doc["rules"]:
            for group in rule["apiGroups"]:
                for resource in rule["resources"]:
                    for verb in rule["verbs"]:
                        out.add((doc["metadata"]["name"], group, resource, verb))
    return out


def adapter_calls():
    """The first positional arguments of every Kubernetes.run(...) in adapter.py."""
    tree = ast.parse((HERE / "adapter.py").read_text())
    calls = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            name = node.args[0].value
            second = (
                node.args[1].value
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
                else None
            )
            calls.add((name, second) if name == "get" else (name,))
    return calls


class RbacTests(unittest.TestCase):
    def test_nothing_is_wildcarded_or_broad(self):
        for doc in DOCS:
            for rule in doc.get("rules", []):
                for field in ("apiGroups", "resources", "verbs"):
                    self.assertNotIn("*", rule[field], doc["metadata"]["name"])
                self.assertNotIn("secrets", rule["resources"])
                for verb in ("delete", "deletecollection", "create", "update", "watch"):
                    if verb == "create" and rule["resources"] == ["pods/exec"]:
                        continue
                    self.assertNotIn(verb, rule["verbs"], doc["metadata"]["name"])

    def test_cluster_wide_grant_is_list_pods_only(self):
        self.assertEqual(
            grants("ClusterRole"), {("pod-label-agent-inventory", "", "pods", "list")}
        )

    def test_namespaced_grants_are_exactly_what_the_adapter_uses(self):
        self.assertEqual(
            grants("Role"),
            {
                ("pod-label-agent", "", "pods", "get"),
                ("pod-label-agent", "", "pods", "patch"),
                ("pod-label-agent", "", "pods/log", "get"),
                ("pod-label-agent-stimulus", "", "pods/exec", "get"),
                ("pod-label-agent-stimulus", "", "pods/exec", "create"),
            },
        )

    def test_adapter_makes_only_calls_these_grants_cover(self):
        self.assertEqual(
            adapter_calls(),
            {("logs",), ("exec",), ("get", "pods"), ("get", "pod"), ("patch",)},
            "the adapter's kubectl calls changed: update rbac/rbac.yaml and this test",
        )

    def test_every_binding_targets_the_one_service_account(self):
        for doc in DOCS:
            if doc["kind"] in {"RoleBinding", "ClusterRoleBinding"}:
                self.assertEqual(
                    doc["subjects"],
                    [{"kind": "ServiceAccount", "name": "pod-label-agent", "namespace": "jev-label-demo"}],
                )

    def test_token_is_not_mounted_into_pods(self):
        account = next(d for d in DOCS if d["kind"] == "ServiceAccount")
        self.assertIs(account["automountServiceAccountToken"], False)


if __name__ == "__main__":
    unittest.main()
