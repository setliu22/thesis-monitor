"""Idempotent local launcher with a detached supervisor. No credentials in state."""

from __future__ import annotations
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "work" / "local-app"
URL = "http://127.0.0.1:5174/"
PYTHON = ROOT / ".venv/bin/python"


def healthy(url: str, marker: bytes) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status == 200 and marker in response.read(50000)
    except (OSError, urllib.error.URLError):
        return False


def running() -> bool:
    with (STATE / "supervisor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def node_binary() -> str:
    choices = [shutil.which("node")]
    choices += [
        str(p) for p in sorted((ROOT / "work").glob("node-v*/bin/node"), reverse=True)
    ]
    for node in choices:
        if node:
            try:
                version = subprocess.check_output(
                    [node, "--version"], text=True, timeout=5
                )
                if int(version.lstrip("v").split(".")[0]) >= 22:
                    return node
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
    raise RuntimeError("Node 22 or newer is required. Install Node, then launch again.")


def supervise() -> None:
    lock = (STATE / "supervisor.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    (STATE / "supervisor.pid").write_text(str(os.getpid()))
    children: dict[str, subprocess.Popen] = {}
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "backend"), PYTHONUNBUFFERED="1")
    try:
        node = node_binary()
        if (
            not PYTHON.exists()
            or not (ROOT / "frontend/node_modules/vite/bin/vite.js").exists()
        ):
            raise RuntimeError(
                "Local dependencies are missing. See README local setup."
            )
        with (STATE / "migrations.log").open("a") as log:
            subprocess.run(
                [
                    str(PYTHON),
                    "-m",
                    "alembic",
                    "-c",
                    "backend/alembic.ini",
                    "upgrade",
                    "head",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                timeout=90,
                check=True,
            )
        commands = {
            "api": [
                str(PYTHON),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            "website": [
                node,
                str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                "5174",
                "--strictPort",
            ],
            "worker": [str(PYTHON), "-m", "app.worker"],
            "email": [str(PYTHON), "-m", "app.notifications"],
        }
        probes = {
            "api": ("http://127.0.0.1:8000/health", b'"ok"'),
            "website": (URL, b"@vite/client"),
        }
        while not stopping:
            for name, command in commands.items():
                child = children.get(name)
                if child and child.poll() is None:
                    continue
                if name in probes and healthy(*probes[name]):
                    continue  # Reuse a compatible service already running on its port.
                if name in ("worker", "email") and not healthy(
                    "http://127.0.0.1:8000/ready", b'"ready"'
                ):
                    continue
                log = (STATE / f"{name}.log").open("a")
                children[name] = subprocess.Popen(
                    command,
                    cwd=ROOT / "frontend" if name == "website" else ROOT,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                )
                log.close()
                print(f"Started {name}", flush=True)
            time.sleep(4)
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
        (STATE / "supervisor.pid").unlink(missing_ok=True)
        lock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supervise", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    if args.supervise:
        supervise()
        return 0
    if args.stop:
        if running():
            os.kill(int((STATE / "supervisor.pid").read_text()), signal.SIGTERM)
            for _ in range(30):
                if not running():
                    break
                time.sleep(1)
            else:
                print(
                    "Local services are still stopping; check the launcher log.",
                    file=sys.stderr,
                )
                return 1
            print("Stopping local services. Cloud monitoring continues independently.")
        else:
            print("Local launcher is not running.")
        return 0
    if not PYTHON.exists():
        print(
            "Python dependencies are missing. See README local setup.", file=sys.stderr
        )
        return 1
    node_binary()
    if not running():
        with (STATE / "launcher.log").open("a") as log:
            subprocess.Popen(
                [str(PYTHON), str(Path(__file__).resolve()), "--supervise"],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
    print("Starting Thesis Monitor…", flush=True)
    for _ in range(90):
        if (
            healthy(URL, b"@vite/client")
            and healthy(URL + "health", b'"ok"')
            and healthy("http://127.0.0.1:8000/ready", b'"ready"')
        ):
            print(f"Ready: {URL}", flush=True)
            if not args.no_open:
                webbrowser.open(URL)
            return 0
        time.sleep(1)
    print(
        f"Startup did not finish. Check {STATE}/launcher.log and service logs.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
