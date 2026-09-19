# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""stop.sh must stop this checkout's generator and leave a foreign one alone.

Starts a decoy `generator2.py` from a DIFFERENT working directory, runs the
real `just down`, and checks the decoy survived. The decoy is this process's
own child: it is tracked by exact PID and terminated in `finally`, whatever
happens. Nothing else is signalled and no files are removed.
"""
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[3]
PKG = REPO / "demos/01-log-triage"
SCRATCH = PKG / ".test-scratch/stop-scope-decoy"
SCRATCH.mkdir(parents=True, exist_ok=True)
(SCRATCH / "generator2.py").write_text("import time\ntime.sleep(300)\n")

def cwd_of(pid):
    out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
    return next((ln[1:] for ln in out.splitlines() if ln.startswith("n")), None)

def ours():
    pids = subprocess.run(["pgrep", "-f", "generator2.py"], capture_output=True, text=True).stdout.split()
    return [int(p) for p in pids if cwd_of(p) == str(PKG)]

decoy = subprocess.Popen([sys.executable, "generator2.py"], cwd=SCRATCH)
try:
    time.sleep(1.5)
    assert cwd_of(decoy.pid) == str(SCRATCH), "decoy cwd not as expected"
    before = ours()
    print(f"decoy pid {decoy.pid} cwd {cwd_of(decoy.pid)}")
    print(f"this checkout's generators before: {before}")
    out = subprocess.run(["just", "down"], cwd=REPO, capture_output=True, text=True, timeout=120)
    for ln in (out.stdout + out.stderr).splitlines():
        if "stray" in ln or "leaving" in ln or ln.strip() == "stopped.":
            print("  stop.sh:", ln.strip())
    time.sleep(1.5)
    after, alive = ours(), decoy.poll() is None
    print(f"this checkout's generators after:  {after}")
    print(f"decoy still alive: {alive}")
    ok = alive and not after and f"leaving pid {decoy.pid} alone" in out.stdout
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
finally:
    decoy.terminate()
    try:
        decoy.wait(5)
    except subprocess.TimeoutExpired:
        decoy.kill()
    print(f"decoy pid {decoy.pid} terminated by its owner (exit {decoy.returncode})")
