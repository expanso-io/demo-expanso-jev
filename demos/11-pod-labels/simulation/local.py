"""Foreground local k3d demo. Cloud processes injected pod events."""

import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

SIM = Path(__file__).resolve().parent
HERE = SIM.parent  # the example itself: adapter.py, pipeline.yaml, edge.yaml
ROOT = HERE.parents[1]
STATE_DIR = ROOT / ".expanso/pod-labels"
CLUSTER = "jev-label-demo"
URL = "http://127.0.0.1:8901"


def environment(home):
    home.mkdir(parents=True, exist_ok=True)
    token_file = home / "local-token"
    if not token_file.exists():
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_hex(32))
    env = dict(os.environ)
    env.update(
        KUBECONFIG=str(home / "kubeconfig"),
        KUBE_CONTEXT=CLUSTER,
        POD_LABEL_NAMESPACES=CLUSTER,
        POD_LABEL_TOKEN=token_file.read_text().strip(),
        POD_LABEL_PORT="8901",
        POD_LABEL_APPLY=os.environ.get("POD_LABEL_APPLY", "true"),
        # The disposable local cluster acts at 80%. The adapter's own default,
        # used anywhere else, stays at 90%.
        POD_LABEL_THRESHOLD=os.environ.get("POD_LABEL_THRESHOLD", "0.8"),
    )
    return env


def fixture_upgrade_targets(pods):
    """Recreate only recognized disposable fixtures for the new workload."""
    targets = []
    for pod in pods:
        meta = pod["metadata"]
        if meta["namespace"] != CLUSTER or meta["name"] not in {
            "checkout-new",
            "checkout-reference",
            "analytics-reference",
            "checkout-api",
            "orders-api",
            "analytics-worker",
        }:
            continue
        annotations = meta.get("annotations", {})
        legacy_analytics = (
            meta["name"] == "analytics-reference"
            and annotations.get("jev.expanso.io/purpose")
            == "Analytics batch worker. Not a checkout service or stable HTTP traffic target."
            and [c["image"] for c in pod["spec"]["containers"]]
            == ["registry.k8s.io/pause:3.10"]
        )
        if (
            annotations.get("jev.expanso.io/fixture") != "visual-v1"
            and not legacy_analytics
        ):
            raise RuntimeError(
                "Refusing to replace an unrecognized pod: " + meta["name"]
            )
        if (
            meta["name"] in {"checkout-api", "orders-api", "analytics-worker"}
            and annotations.get("jev.expanso.io/workload-version") == "signals-v7"
        ):
            continue
        targets.append(meta["name"])
    return targets


def require_free_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(
                f"Port {port} already in use; stop its owner first"
            ) from exc


class Session:
    def __init__(self):
        self.env = environment(STATE_DIR)
        self.children = []
        self.logs = []
        self.cluster_started = False
        self.docker_started = False
        self.cloud_job = None
        self.deployment_attempted = False

    def run(self, *args, timeout=180, env=None):
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode:
            # Commands never carry credentials in argv.
            raise RuntimeError(f"{' '.join(args[:3])} failed: {result.stderr.strip()}")
        return result.stdout

    def start(self, name, *args, env=None):
        path = STATE_DIR / (name + ".log")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        log = os.fdopen(fd, "w")
        self.logs.append(log)
        process = subprocess.Popen(
            args,
            cwd=ROOT,
            env=env or self.env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.children.append((name, process))

    def healthy(self):
        for name, child in self.children:
            if child.poll() is not None:
                raise RuntimeError(
                    f"{name} exited; inspect {STATE_DIR / (name + '.log')}"
                )

    def wait(self, message, predicate, timeout=180):
        print(message, flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.healthy()
            if predicate():
                return
            time.sleep(2)
        raise RuntimeError(message + " timed out; inspect .expanso/pod-labels/*.log")

    def state(self):
        try:
            with urllib.request.urlopen(URL + "/api/state", timeout=50) as response:
                return json.load(response)
        except (OSError, ValueError):
            return {}

    def connected(self):
        connection = STATE_DIR / "config.d/50-connection.yaml"
        if not connection.exists():
            return False
        ids = re.findall(
            r"(?m)^\s*node_id:\s*[\"']?([0-9a-f-]{36})", connection.read_text()
        )
        output = self.run(
            "expanso-cli",
            "node",
            "list",
            "--label",
            "demo=jev-pod-labels",
            "--limit",
            "2",
            "--format",
            "json",
            timeout=30,
        )
        nodes = json.JSONDecoder().raw_decode(output.lstrip())[0]
        return (
            len(nodes) == 1
            and ids == [nodes[0]["id"]]
            and nodes[0]["status"]["connection_state"] == "connected"
        )

    def job(self):
        try:
            output = self.run(
                "expanso-cli",
                "job",
                "describe",
                "jev-pod-labels",
                "--namespace",
                "demo",
                "--format",
                "json",
                timeout=15,
            )
        except RuntimeError as exc:
            if "not found" in str(exc).lower():
                return None
            raise
        return json.JSONDecoder().raw_decode(output.lstrip())[0]

    def up(self):
        for tool in ("uv", "docker", "k3d", "kubectl", "expanso-cli", "expanso-edge"):
            if not shutil.which(tool):
                raise RuntimeError(f"Install {tool} before starting the pod demo")
        for key in (
            "EXPANSO_CLI_ENDPOINT",
            "EXPANSO_CLI_AUTH_API_KEY",
            "EXPANSO_EDGE_BOOTSTRAP_TOKEN",
            "TYPESAFE_API_KEY",
        ):
            if not self.env.get(key):
                raise RuntimeError(f"Set {key} in the repository-root .env")
        existing = self.job()
        if existing and existing["status"]["state"]["state_type"] != "stopped":
            raise RuntimeError(
                "Cloud pod job is already active; stop it before starting a new session"
            )
        require_free_port(8901)
        require_free_port(9016)
        print("Starting POD LABELS (11), using k3d + Expanso Cloud", flush=True)
        try:
            self.run("docker", "info", timeout=15)
        except (RuntimeError, subprocess.TimeoutExpired):
            if sys.platform != "darwin":
                raise RuntimeError("Start Docker, then rerun just up") from None
            self.docker_started = True
            print("Starting Docker Desktop…", flush=True)
            self.run("docker", "desktop", "start", "--timeout", "90", timeout=100)
        clusters = json.loads(self.run("k3d", "cluster", "list", "-o", "json"))
        exists = any(cluster["name"] == CLUSTER for cluster in clusters)
        running = self.run(
            "docker",
            "ps",
            "--filter",
            "label=k3d.cluster=" + CLUSTER,
            "--format",
            "{{.ID}}",
        ).strip()
        if not exists:
            self.cluster_started = True
            print("Creating disposable k3s cluster…", flush=True)
            self.run(
                "k3d",
                "cluster",
                "create",
                CLUSTER,
                "--kubeconfig-update-default=false",
                "--kubeconfig-switch-context=false",
                "--wait",
            )
        elif not running:
            self.cluster_started = True
            print("Starting existing demo cluster…", flush=True)
            self.run("k3d", "cluster", "start", CLUSTER, "--wait", "--timeout", "120s")
        kubeconfig = Path(self.env["KUBECONFIG"])
        fd = os.open(kubeconfig, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(self.run("k3d", "kubeconfig", "get", CLUSTER))
        self.run("kubectl", "config", "rename-context", "k3d-" + CLUSTER, CLUSTER)
        inventory = json.loads(
            self.run(
                "kubectl",
                "--context",
                CLUSTER,
                "get",
                "pods",
                "--all-namespaces",
                "-o",
                "json",
            )
        )
        for name in fixture_upgrade_targets(inventory["items"]):
            print(
                f"Upgrading disposable fixture {name} to the event workload…",
                flush=True,
            )
            self.run(
                "kubectl",
                "--context",
                CLUSTER,
                "-n",
                CLUSTER,
                "delete",
                "pod",
                name,
                "--wait=true",
            )
        self.run(
            "kubectl", "--context", CLUSTER, "apply", "-f", str(SIM / "fixtures.yaml")
        )
        self.run(
            "kubectl",
            "--context",
            CLUSTER,
            "-n",
            CLUSTER,
            "wait",
            "pod",
            "--all",
            "--for=condition=Ready",
            "--timeout=180s",
            timeout=190,
        )
        self.start("adapter", "uv", "run", str(HERE / "adapter.py"))
        self.wait(
            "Waiting for local adapter and Kubernetes…",
            lambda: bool(self.state().get("pods")),
        )
        edge_env = dict(self.env)
        for key in ("TYPESAFE_API_KEY", "EXPANSO_EDGE_HOME"):
            edge_env.pop(key, None)
        if not (STATE_DIR / "config.d/50-connection.yaml").exists():
            self.run(
                "expanso-edge", "bootstrap", "--data-dir", str(STATE_DIR), env=edge_env
            )
        self.start(
            "edge",
            "expanso-edge",
            "run",
            "--data-dir",
            str(STATE_DIR),
            "--api-listen",
            "127.0.0.1:9016",
            "--config",
            str(HERE / "edge.yaml"),
            env=edge_env,
        )
        self.wait(
            "Waiting for this Edge node in Expanso Cloud (usually 40–60s)…",
            self.connected,
        )
        self.deployment_attempted = True
        self.run("uv", "run", str(HERE / "deploy.py"), timeout=100)
        deployed = self.job()
        self.cloud_job = (deployed["id"], deployed["status"]["version"])
        self.wait(
            "Waiting for Cloud execution on this node…",
            lambda: self.state().get("cloud", {}).get("state") == "running",
        )
        print(
            f"\nREADY: {URL}\nChoose an event, then click any pod. Ctrl-C stops this session.\n"
            f"Label writes: {self.env['POD_LABEL_APPLY']}. Logs: {STATE_DIR}",
            flush=True,
        )
        while True:
            self.healthy()
            time.sleep(2)

    def close(self):
        print("Stopping this pod-demo session…", flush=True)
        unresolved = self.deployment_attempted and not self.cloud_job
        if self.cloud_job:
            try:
                current = self.job()
                identity = (
                    (current["id"], current["status"]["version"]) if current else None
                )
                if identity != self.cloud_job:
                    raise RuntimeError(
                        "Cloud job changed ownership/version; leaving it untouched"
                    )
                self.run(
                    "expanso-cli",
                    "job",
                    "stop",
                    "jev-pod-labels",
                    "--namespace",
                    "demo",
                    "--force",
                    timeout=30,
                )
            except Exception as exc:
                print(f"Cloud stop failed: {exc}", file=sys.stderr)
        for _, child in reversed(self.children):
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                except ProcessLookupError:
                    pass
        for stream in self.logs:
            stream.close()
        if self.cluster_started:
            try:
                self.run("k3d", "cluster", "stop", CLUSTER)
            except Exception as exc:
                print(f"Cluster stop failed: {exc}", file=sys.stderr)
        if self.docker_started:
            try:
                if not self.run("docker", "ps", "-q").strip():
                    self.run("docker", "desktop", "stop", "--timeout", "45", timeout=50)
            except Exception as exc:
                print(f"Docker stop failed: {exc}", file=sys.stderr)

        if unresolved:
            raise RuntimeError(
                "Cloud submission outcome is unverified. Run root "
                "just pod-labels-status and stop this job with just pod-labels-stop "
                "if it was submitted. Local services have been stopped."
            )


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / "local.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if sys.argv[1:] != ["down"]:
                raise RuntimeError(
                    "Pod demo already running; use just down first"
                ) from None
            lock.seek(0)
            pid = int(lock.read())
            command = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "command="], text=True
            )
            if str(Path(__file__).resolve()) not in command:
                raise RuntimeError(
                    "Launcher identity mismatch; refusing to signal process"
                )
            os.kill(pid, signal.SIGTERM)
            print("Stop requested; the up terminal will report cleanup.")
            return
        if sys.argv[1:] == ["down"]:
            print("No pod-demo launcher running.")
            return
        if sys.argv[1:] != ["up"]:
            raise RuntimeError("Usage: local.py up|down")
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()

        def stop(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        session = Session()
        try:
            session.up()
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            session.close()
            lock.seek(0)
            lock.truncate()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Pod demo could not start: {exc}", file=sys.stderr)
        sys.exit(1)
