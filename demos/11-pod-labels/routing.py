"""Read actual Service membership; never infer it from desired pod labels."""


def membership(kube, namespace="jev-label-demo"):
    result = {
        "service": "stable-checkout",
        "namespace": namespace,
        "state": "unavailable",
        "pods": [],
    }
    try:
        service = kube.run(
            "get", "service", "stable-checkout", "-n", namespace, "-o", "json"
        )
        slices = kube.run(
            "get",
            "endpointslices",
            "-n",
            namespace,
            "-l",
            "kubernetes.io/service-name=stable-checkout",
            "-o",
            "json",
        )
        result.update(
            state="observed",
            selector=service["spec"].get("selector", {}),
            pods=sorted(
                {
                    endpoint["targetRef"]["name"]
                    for item in slices["items"]
                    for endpoint in (item.get("endpoints") or [])
                    if endpoint.get("conditions", {}).get("ready") is True
                    and endpoint.get("addresses")
                    and endpoint.get("targetRef", {}).get("kind") == "Pod"
                }
            ),
        )
    except (RuntimeError, KeyError, TypeError, AttributeError):
        result["reason"] = "Service membership could not be read"
    return result
