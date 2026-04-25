"""Manages running CTF challenge subprocesses.

Each challenge is a small Flask app that binds to its own port. Launching
a challenge:
  1. Installs requirements.txt (synchronously, once).
  2. Starts `python app.py` as a background subprocess.
  3. Polls the port until it's listening (up to ~5 seconds).
  4. Returns status so the UI can redirect the user.

State lives in-memory for the lifetime of the SecScenario server. Stopping
SecScenario leaves orphan challenge processes behind; re-launching a
challenge detects the port is in use and simply reports "running".
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil


# Env vars that MUST be scrubbed before spawning a child Flask app, otherwise
# Werkzeug tries to reuse an inherited socket FD and crashes on Windows
# (WinError 10038: operation attempted on something that is not a socket).
_ENV_BLOCKLIST = {
    "WERKZEUG_SERVER_FD",
    "WERKZEUG_RUN_MAIN",
    "FLASK_RUN_FROM_CLI",
    "FLASK_APP",
    "FLASK_DEBUG",
    "FLASK_ENV",
}


def _child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _ENV_BLOCKLIST}
    # Force unbuffered output so the runtime.log updates live
    env["PYTHONUNBUFFERED"] = "1"
    return env


# challenge_id -> dict(proc, port, folder, log_path, state, started_at)
_running: dict[int, dict] = {}


def launch(challenge_id: int, folder_path: str, port: int) -> dict:
    folder = Path(folder_path)
    if not folder.exists():
        raise RuntimeError(f"Challenge folder missing: {folder}")

    app_py = folder / "app.py"
    if not app_py.exists():
        raise RuntimeError("No app.py found in challenge folder.")

    # Already tracked and alive AND bound to port AND serving THIS folder?
    existing = _running.get(challenge_id)
    if existing and existing.get("proc") and existing["proc"].poll() is None \
            and _is_port_up(port) and existing.get("folder") == folder:
        existing["state"] = "running"
        return _snapshot(existing)

    # Any orphan listening on this port (from deleted challenges, stale
    # subprocesses, prior SecScenario runs)? Kill so the right app binds.
    if _is_port_up(port):
        kill_port(port)
    # Drop any stale in-memory entry so we start fresh.
    _running.pop(challenge_id, None)

    # Install deps (quiet, bounded)
    req = folder / "requirements.txt"
    install_log = ""
    if req.exists():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req)],
                cwd=str(folder),
                capture_output=True,
                text=True,
                timeout=180,
            )
            install_log = (result.stdout or "") + (result.stderr or "")
        except subprocess.TimeoutExpired:
            install_log = "[pip install timed out after 180s]\n"
        except Exception as e:
            install_log = f"[pip install error: {e}]\n"

    log_path = folder / "runtime.log"
    log_path.write_text(
        f"=== SecScenario launcher ===\n"
        f"pip install output:\n{install_log}\n"
        f"=== starting app.py on 127.0.0.1:{port} ===\n",
        encoding="utf-8",
    )
    log_handle = open(log_path, "a", encoding="utf-8")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", "app.py"],
            cwd=str(folder),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            env=_child_env(),
        )
    except Exception as e:
        log_handle.close()
        raise RuntimeError(f"Could not start subprocess: {e}")

    entry = {
        "proc": proc,
        "port": port,
        "folder": folder,
        "log_path": log_path,
        "state": "starting",
        "started_at": time.time(),
    }
    _running[challenge_id] = entry

    # Poll for port up (up to ~5s)
    for _ in range(25):
        time.sleep(0.2)
        if _is_port_up(port):
            entry["state"] = "running"
            return _snapshot(entry)
        if proc.poll() is not None:
            entry["state"] = "crashed"
            return _snapshot(entry)

    # Still starting — let UI poll
    return _snapshot(entry)


def stop(challenge_id: int, port: int | None = None) -> bool:
    """Terminate the challenge. Kill by PID if tracked, else kill by port."""
    entry = _running.get(challenge_id)
    target_port = port
    if entry and target_port is None:
        target_port = entry.get("port")

    # 1) Try to terminate tracked subprocess + its children.
    if entry and entry.get("proc") and entry["proc"].poll() is None:
        proc = entry["proc"]
        try:
            ps_proc = psutil.Process(proc.pid)
            for ch in ps_proc.children(recursive=True):
                try:
                    ch.kill()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if sys.platform == "win32":
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    proc.terminate()
            else:
                proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # 2) Anything still listening on the port? Nuke it.
    if target_port and _is_port_up(target_port):
        kill_port(target_port)

    if entry:
        entry["state"] = "stopped"
    return True


def status(challenge_id: int, port: int) -> dict:
    entry = _running.get(challenge_id)
    if not entry:
        # we have no record, but maybe something is bound to that port
        if _is_port_up(port):
            return {"state": "running", "port": port, "externally_running": True}
        return {"state": "stopped", "port": port}

    proc = entry.get("proc")
    if proc is None:
        entry["state"] = "running" if _is_port_up(port) else "stopped"
        return _snapshot(entry)

    rc = proc.poll()
    if rc is None:
        if _is_port_up(port):
            entry["state"] = "running"
        elif entry["state"] != "starting" and time.time() - entry["started_at"] > 6:
            entry["state"] = "crashed"
        return _snapshot(entry)

    entry["state"] = "crashed" if rc != 0 else "stopped"
    return _snapshot(entry)


def tail_log(challenge_id: int, max_lines: int = 60) -> str:
    entry = _running.get(challenge_id)
    if not entry:
        return ""
    path = entry.get("log_path")
    if not path or not Path(path).exists():
        return ""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _pids_on_port(port: int) -> list[int]:
    """Return PIDs of processes currently listening on the given TCP port.

    Best-effort only: any introspection failure (restricted /proc inside
    containers, OS quirks, missing perms) yields an empty list rather than
    raising, since the caller falls back to a port-availability check.
    """
    pids: set[int] = set()
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port and c.pid:
                pids.add(c.pid)
        return list(pids)
    except Exception:
        pass
    try:
        for proc in psutil.process_iter(attrs=["pid"]):
            try:
                conns = proc.net_connections(kind="tcp") if hasattr(proc, "net_connections") \
                    else proc.connections(kind="tcp")
                for c in conns:
                    if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port:
                        pids.add(proc.info["pid"])
            except Exception:
                continue
    except Exception:
        pass
    return list(pids)


def kill_port(port: int) -> int:
    """Terminate every process listening on `port`. Returns count killed."""
    pids = _pids_on_port(port)
    killed = 0
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            # Kill children first (Flask reloader spawns one)
            for ch in proc.children(recursive=True):
                try:
                    ch.kill()
                except Exception:
                    pass
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # Wait a beat for the OS to release the socket
    for _ in range(10):
        if not _is_port_up(port):
            break
        time.sleep(0.1)
    return killed


def _is_port_up(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.2)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _snapshot(entry: dict) -> dict:
    return {
        "state": entry.get("state", "unknown"),
        "port": entry.get("port"),
        "pid": entry["proc"].pid if entry.get("proc") else None,
    }
