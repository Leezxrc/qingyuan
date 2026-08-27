import os
import subprocess
import time
from urllib.request import urlopen


# ============================================================
# Paths
# ============================================================

TTS_DIR = r"C:\MyAgent\CosyVoice"
TTS_PYTHON = r"C:\MyAgent\cosyvoice_env\Scripts\python.exe"
TTS_SCRIPT = r"C:\MyAgent\CosyVoice\qingyuan_tts_server.py"
TTS_HEALTH = "http://127.0.0.1:8765/health"

STT_DIR = r"C:\MyAgent"
STT_PYTHON = r"C:\MyAgent\stt_env\Scripts\python.exe"
STT_SCRIPT = r"C:\MyAgent\qingyuan_stt_server.py"
STT_HEALTH = "http://127.0.0.1:8766/health"

AGENT_DIR = r"C:\MyAgent"
AGENT_PYTHON = r"C:\MyAgent\.venv\Scripts\python.exe"
AGENT_SCRIPT = r"C:\MyAgent\agent.py"
AGENT_HEALTH = "http://127.0.0.1:8767/health"

TRAY_DIR = r"C:\MyAgent"
TRAY_PYTHONW = r"C:\MyAgent\.venv\Scripts\pythonw.exe"
TRAY_SCRIPT = r"C:\MyAgent\qingyuan_tray.py"


# ============================================================
# Windows flags
# ============================================================

CREATE_NEW_CONSOLE = getattr(
    subprocess,
    "CREATE_NEW_CONSOLE",
    0,
)

STARTF_USESHOWWINDOW = getattr(
    subprocess,
    "STARTF_USESHOWWINDOW",
    1,
)

SW_SHOWMINIMIZED = 2


# ============================================================
# Helpers
# ============================================================

def health_ok(
    url: str
) -> bool:

    try:

        with urlopen(
            url,
            timeout=1.0,
        ) as response:

            return (
                response.status
                == 200
            )

    except Exception:

        return False


def require_file(
    path: str,
    label: str,
) -> bool:

    if os.path.isfile(path):
        return True

    print(
        f"[ERROR] {label} not found:"
    )
    print(path)
    print()

    return False


def minimized_startupinfo():

    info = subprocess.STARTUPINFO()

    info.dwFlags |= (
        STARTF_USESHOWWINDOW
    )

    info.wShowWindow = (
        SW_SHOWMINIMIZED
    )

    return info


def start_python_console(
    python_exe: str,
    script: str,
    cwd: str,
    minimized: bool = False,
):

    kwargs = {
        "cwd": cwd,
        "creationflags": (
            CREATE_NEW_CONSOLE
        ),
    }

    if minimized:

        kwargs["startupinfo"] = (
            minimized_startupinfo()
        )

    # IMPORTANT:
    # Directly execute python.exe.
    # Do NOT go through cmd.exe /k.
    return subprocess.Popen(
        [
            python_exe,
            script,
        ],
        **kwargs,
    )


def wait_for_service(
    name: str,
    url: str,
    timeout_seconds: float,
):

    deadline = (
        time.time()
        + timeout_seconds
    )

    while time.time() < deadline:

        if health_ok(url):

            print(
                f"[OK] {name} ready."
            )

            return True

        time.sleep(0.5)

    print(
        f"[ERROR] {name} did not become ready."
    )

    return False


# ============================================================
# Main
# ============================================================

def request_shutdown(
    url: str,
) -> None:

    try:

        with urlopen(
            url,
            timeout=1.5,
        ) as response:

            response.read()

    except Exception:
        pass


def wait_for_agent_exit(
    agent_process,
) -> None:
    """
    常驻后台监督 Agent 生命周期。

    即使用户直接点 X 关闭 Agent 主窗口，
    也能检测到并收掉 STT / TTS / Tray。
    """

    while True:

        if (
            agent_process is not None
            and agent_process.poll() is not None
        ):

            return


        if not health_ok(
            AGENT_HEALTH
        ):

            # 排除极短暂的连接抖动。
            time.sleep(1.0)

            if not health_ok(
                AGENT_HEALTH
            ):

                return


        time.sleep(0.8)


def main():

    required = [
        (TTS_PYTHON, "CosyVoice Python"),
        (TTS_SCRIPT, "TTS server"),
        (STT_PYTHON, "STT Python"),
        (STT_SCRIPT, "STT server"),
        (AGENT_PYTHON, "Agent Python"),
        (AGENT_SCRIPT, "Agent"),
        (TRAY_PYTHONW, "Tray Python"),
        (TRAY_SCRIPT, "Tray app"),
    ]


    for path, label in required:

        if not require_file(
            path,
            label,
        ):

            return


    tts_process = None
    stt_process = None
    agent_process = None
    tray_process = None


    try:

        # TTS
        if not health_ok(
            TTS_HEALTH
        ):

            tts_process = start_python_console(
                TTS_PYTHON,
                TTS_SCRIPT,
                TTS_DIR,
                minimized=True,
            )


        # STT
        if not health_ok(
            STT_HEALTH
        ):

            stt_process = start_python_console(
                STT_PYTHON,
                STT_SCRIPT,
                STT_DIR,
                minimized=True,
            )


        if not wait_for_service(
            "TTS",
            TTS_HEALTH,
            120,
        ):

            return


        if not wait_for_service(
            "STT",
            STT_HEALTH,
            120,
        ):

            return


        # Agent
        if not health_ok(
            AGENT_HEALTH
        ):

            agent_process = start_python_console(
                AGENT_PYTHON,
                AGENT_SCRIPT,
                AGENT_DIR,
                minimized=False,
            )


        if not wait_for_service(
            "Agent",
            AGENT_HEALTH,
            30,
        ):

            return


        # Tray
        tray_process = subprocess.Popen(
            [
                TRAY_PYTHONW,
                TRAY_SCRIPT,
            ],
            cwd=TRAY_DIR,
        )


        # Launcher 留在后台监督 Agent。
        wait_for_agent_exit(
            agent_process
        )


    finally:

        # Agent 不在 = 清渊整体应该退出。
        request_shutdown(
            "http://127.0.0.1:8766/shutdown"
        )

        request_shutdown(
            "http://127.0.0.1:8765/shutdown"
        )


        if (
            tray_process is not None
            and tray_process.poll() is None
        ):

            try:
                tray_process.terminate()
            except Exception:
                pass


        time.sleep(1.0)


        # 如果优雅关闭失败，用本次启动得到的进程句柄兜底。
        for process in [
            stt_process,
            tts_process,
        ]:

            if (
                process is not None
                and process.poll() is None
            ):

                try:
                    process.terminate()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
