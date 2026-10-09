"""Real fixture processes prove ownership checks preserve unrelated processes."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stop_owned", ROOT / "stop-owned.py")
owned = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owned)


class StopOwnedTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.directory.name).resolve()
        self.pidfile = self.root / "fixture.pid"
        self.process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)", "owned-fixture"],
            cwd=self.root,
        )
        self.pidfile.write_text(str(self.process.pid))

    def tearDown(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        self.directory.cleanup()

    def test_recorded_process_stops(self):
        owned.record(self.pidfile, self.root, "owned-fixture")
        self.assertNotIn("owned-fixture", owned.sidecar(self.pidfile).read_text())
        owned.stop(self.pidfile, self.root, "owned-fixture")
        self.process.wait(timeout=5)
        self.assertFalse(self.pidfile.exists())

    def test_legacy_pid_refuses(self):
        with self.assertRaisesRegex(ValueError, "No saved process identity"):
            owned.stop(self.pidfile, self.root, "owned-fixture")
        self.assertIsNone(self.process.poll())

    def test_stale_start_time_refuses(self):
        owned.record(self.pidfile, self.root, "owned-fixture")
        saved = json.loads(owned.sidecar(self.pidfile).read_text())
        saved["start"] = "stale process start"
        owned.sidecar(self.pidfile).write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError, "belongs to another process"):
            owned.stop(self.pidfile, self.root, "owned-fixture")
        self.assertIsNone(self.process.poll())

    def test_other_checkout_refuses(self):
        owned.record(self.pidfile, self.root, "owned-fixture")
        with self.assertRaisesRegex(ValueError, "belongs to another process"):
            owned.stop(self.pidfile, ROOT, "owned-fixture")
        self.assertIsNone(self.process.poll())

    def test_wrong_command_refuses(self):
        owned.record(self.pidfile, self.root, "owned-fixture")
        with self.assertRaisesRegex(ValueError, "belongs to another process"):
            owned.stop(self.pidfile, self.root, "different-command")
        self.assertIsNone(self.process.poll())

    def test_owned_descendant_stops(self):
        self.process.terminate()
        self.process.wait(timeout=5)
        code = (
            "import subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "print(p.pid,flush=True); time.sleep(60)"
        )
        self.process = subprocess.Popen(
            [sys.executable, "-c", code, "owned-fixture"],
            cwd=self.root,
            stdout=subprocess.PIPE,
            text=True,
        )
        child = int(self.process.stdout.readline())
        self.pidfile.write_text(str(self.process.pid))
        try:
            owned.record(self.pidfile, self.root, "owned-fixture")
            owned.stop(self.pidfile, self.root, "owned-fixture")
            self.process.wait(timeout=5)
            self.assertIsNone(owned.identity(child))
        finally:
            if owned.identity(child):
                import os
                import signal

                os.kill(child, signal.SIGTERM)
            self.process.stdout.close()


if __name__ == "__main__":
    unittest.main()
