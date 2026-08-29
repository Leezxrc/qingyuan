"""
Qingyuan one-click launcher.

Daily mode:
- packaged as Qingyuan.exe (windowless)
- starts TTS, STT, Frontend, Tray
- Frontend starts matching Brain Backend automatically
- Frontend v5.5+ starts Desktop Pet automatically
- supervises the Frontend and shuts down child services when it exits

This launcher intentionally does NOT bundle models, environments or user data.
It orchestrates the existing C:\\MyAgent installation.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


# ============================================================
# Base directory
# ============================================================

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

TTS_DIR = BASE_DIR / "CosyVoice"
TTS_PYTHON = BASE_DIR / "cosyvoice_env" / "Scripts" / "python.exe"
TTS_SCRIPT = TTS_DIR / "qingyuan_tts_server.py"
TTS_HEALTH = "http://127.0.0.1:8765/health"

STT_DIR = BASE_DIR
STT_PYTHON = Path(r"C:\Users\leezx\miniconda3\envs\chatAudio\python.exe")
STT_SCRIPT = BASE_DIR / "qingyuan_stt_server.py"
STT_HEALTH = "http://127.0.0.1:8766/health"

AGENT_DIR = BASE_DIR
AGENT_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
AGENT_PYTHONW = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
AGENT_SCRIPT = BASE_DIR / "agent.py"
AGENT_HEALTH = "http://127.0.0.1:8767/health"

BACKEND_HEALTH = "http://127.0.0.1:8770/health"
BACKEND_SHUTDOWN = "http://127.0.0.1:8770/shutdown"

TRAY_DIR = BASE_DIR
TRAY_PYTHONW = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
TRAY_SCRIPT = BASE_DIR / "qingyuan_tray.py"

# Launcher itself uses a private local port only as a single-instance lock.
SINGLE_INSTANCE_HOST = "127.0.0.1"
SINGLE_INSTANCE_PORT = 8779

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "qingyuan_launcher.log"
LOG_CLEANUP_MARKER = LOG_DIR / ".last_weekly_cleanup"
LOG_RETENTION_SECONDS = 7 * 24 * 60 * 60

TTS_STARTUP_LOG = LOG_DIR / "tts_startup.log"
STT_STARTUP_LOG = LOG_DIR / "stt_startup.log"
FRONTEND_STARTUP_LOG = LOG_DIR / "frontend_startup.log"
TRAY_STARTUP_LOG = LOG_DIR / "tray_startup.log"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_instance_socket = None


# ============================================================
# Logging
# ============================================================

def _weekly_log_cleanup() -> None:
    """
    每 7 天清理一次 logs 目录中的 *.log。

    只清理日志，不触碰 data / memory / knowledge / skills 等持久化数据。
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()

        last_cleanup = 0.0
        if LOG_CLEANUP_MARKER.exists():
            try:
                last_cleanup = float(
                    LOG_CLEANUP_MARKER.read_text(encoding="utf-8").strip() or "0"
                )
            except Exception:
                last_cleanup = 0.0

        if (now - last_cleanup) < LOG_RETENTION_SECONDS:
            return

        for item in LOG_DIR.glob("*.log"):
            try:
                item.unlink()
            except Exception:
                pass

        LOG_CLEANUP_MARKER.write_text(str(now), encoding="utf-8")
    except Exception:
        pass


def _prepare_log() -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _weekly_log_cleanup()
    except Exception:
        pass


def log(message: str) -> None:
    try:
        _prepare_log()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


# ============================================================
# Helpers
# ============================================================

def acquire_single_instance() -> bool:
    global _instance_socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT))
        sock.listen(1)
        _instance_socket = sock
        return True
    except OSError:
        return False


def health_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def require_file(path: Path, label: str) -> bool:
    if path.is_file():
        return True
    log(f"ERROR: {label} not found: {path}")
    return False


def hidden_python(
    python_exe: Path,
    script: Path,
    cwd: Path,
    startup_log: Path,
):
    """启动隐藏子进程，并把 stdout/stderr 保存到独立启动日志。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    handle = startup_log.open(
        "a",
        encoding="utf-8",
        errors="replace",
    )

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    handle.write(
        f"\n[{stamp}] START: {python_exe} {script}\n"
    )
    handle.flush()

    try:
        process = subprocess.Popen(
            [str(python_exe), str(script)],
            cwd=str(cwd),
            shell=False,
            creationflags=CREATE_NO_WINDOW,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    finally:
        # Windows 已为子进程复制文件句柄，父进程可安全关闭。
        handle.close()

    return process


def wait_for_service(
    name: str,
    url: str,
    timeout_seconds: float,
    process=None,
    startup_log: Path | None = None,
) -> bool:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if health_ok(url):
            log(f"OK: {name} ready")
            return True

        if process is not None:
            try:
                code = process.poll()
            except Exception:
                code = None

            if code is not None:
                suffix = (
                    f"; see {startup_log}"
                    if startup_log is not None
                    else ""
                )
                log(
                    f"ERROR: {name} exited early with code {code}{suffix}"
                )
                return False

        time.sleep(0.4)

    suffix = (
        f"; see {startup_log}"
        if startup_log is not None
        else ""
    )
    log(f"ERROR: {name} did not become ready{suffix}")
    return False


def request_get(url: str) -> None:
    try:
        with urlopen(url, timeout=1.5) as response:
            response.read()
    except Exception:
        pass


def request_post_empty(url: str) -> None:
    # Backend /shutdown is POST. Keep stdlib-only so launcher stays tiny.
    try:
        from urllib.request import Request
        req = Request(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=1.5) as response:
            response.read()
    except Exception:
        pass


def wait_for_agent_exit(agent_process) -> None:
    while True:
        if agent_process is not None and agent_process.poll() is not None:
            return

        if not health_ok(AGENT_HEALTH):
            time.sleep(1.0)
            if not health_ok(AGENT_HEALTH):
                return

        time.sleep(0.8)


def terminate_if_running(process) -> None:
    if process is None:
        return
    try:
        if process.poll() is None:
            process.terminate()
    except Exception:
        pass


# ============================================================
# Main
# ============================================================

def main() -> int:
    _prepare_log()

    if not acquire_single_instance():
        # Already running. Treat as success instead of spawning a second supervisor.
        log("Launcher already running; exiting duplicate instance")
        return 0

    required = [
        (TTS_PYTHON, "CosyVoice Python"),
        (TTS_SCRIPT, "TTS server"),
        (STT_PYTHON, "STT Python"),
        (STT_SCRIPT, "STT server"),
        (AGENT_PYTHON, "Agent Python"),
        (AGENT_SCRIPT, "Agent entry"),
        (TRAY_PYTHONW, "Tray Python"),
        (TRAY_SCRIPT, "Tray app"),
    ]

    for path, label in required:
        if not require_file(path, label):
            return 2

    tts_process = None
    stt_process = None
    agent_process = None
    tray_process = None

    log(f"Qingyuan launcher start; base={BASE_DIR}")

    try:
        if not health_ok(TTS_HEALTH):
            tts_process = hidden_python(
                TTS_PYTHON,
                TTS_SCRIPT,
                TTS_DIR,
                TTS_STARTUP_LOG,
            )

        if not health_ok(STT_HEALTH):
            stt_process = hidden_python(
                STT_PYTHON,
                STT_SCRIPT,
                STT_DIR,
                STT_STARTUP_LOG,
            )

        if not wait_for_service(
            "TTS", TTS_HEALTH, 300,
            process=tts_process, startup_log=TTS_STARTUP_LOG,
        ):
            return 3

        if not wait_for_service(
            "STT", STT_HEALTH, 300,
            process=stt_process, startup_log=STT_STARTUP_LOG,
        ):
            return 4

        if not health_ok(AGENT_HEALTH):
            agent_exe = AGENT_PYTHONW if AGENT_PYTHONW.is_file() else AGENT_PYTHON
            agent_process = hidden_python(
                agent_exe,
                AGENT_SCRIPT,
                AGENT_DIR,
                FRONTEND_STARTUP_LOG,
            )

        if not wait_for_service(
            "Frontend", AGENT_HEALTH, 120,
            process=agent_process, startup_log=FRONTEND_STARTUP_LOG,
        ):
            return 5

        # Frontend is responsible for starting a matching Brain Backend.
        # Do not make launcher depend on Backend being local forever.
        if health_ok(BACKEND_HEALTH):
            log("OK: Brain Backend ready")
        else:
            log("INFO: Brain Backend not yet visible; Frontend may be using/reconnecting backend")

        # Tray has its own single-instance guard.
        try:
            tray_log_handle = TRAY_STARTUP_LOG.open(
                "a", encoding="utf-8", errors="replace"
            )
            try:
                tray_process = subprocess.Popen(
                    [str(TRAY_PYTHONW), str(TRAY_SCRIPT)],
                    cwd=str(TRAY_DIR),
                    shell=False,
                    creationflags=CREATE_NO_WINDOW,
                    stdout=tray_log_handle,
                    stderr=subprocess.STDOUT,
                )
            finally:
                tray_log_handle.close()
        except Exception as exc:
            log(f"WARNING: tray start failed: {exc}")

        log("Qingyuan is ready")
        wait_for_agent_exit(agent_process)
        return 0

    except Exception as exc:
        log(f"FATAL: {type(exc).__name__}: {exc}")
        return 10

    finally:
        log("Qingyuan launcher shutting down child services")

        request_get("http://127.0.0.1:8766/shutdown")
        request_get("http://127.0.0.1:8765/shutdown")

        # Normally Frontend shuts down a locally-started Backend itself.
        # This is only a crash-cleanup fallback.
        if health_ok(BACKEND_HEALTH):
            request_post_empty(BACKEND_SHUTDOWN)

        terminate_if_running(tray_process)
        time.sleep(0.8)
        terminate_if_running(stt_process)
        terminate_if_running(tts_process)

        log("Qingyuan launcher stopped")


if __name__ == "__main__":
    raise SystemExit(main())
