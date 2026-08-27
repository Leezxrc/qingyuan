import os
import queue
import re
import subprocess
import sys
import threading
import time

from .action_host import (
    LocalActionHost,
)
from .config import (
    ACTIVE_WINDOW_SECONDS,
    MODEL_NUM_CTX,
    WORKSPACE,
)
from .control import (
    start_control_server,
)
from .desktop import (
    DesktopController,
)
from .ipc_config import (
    ACTION_URL,
    AUTO_SHUTDOWN_LOCAL_BACKEND,
    AUTO_START_LOCAL_BACKEND,
    BACKEND_URL,
)
from .ipc_http import (
    get_json,
    post_json,
)
from .permission import (
    TaskPermissionBroker,
)
from .runtime import RuntimeState
from .system_tools import SystemTools
from .temp_cleanup import (
    TempCleanupService,
)
from .vision import VisionService
from .voice import VoiceService
from .wake import (
    is_standby_phrase,
    normalize_command,
)
from .wechat import WeChatTools
from .workspace import WorkspaceTools
from .version import (
    BACKEND_PROTOCOL_VERSION,
    QINGYUAN_VERSION,
)


def _backend_health():
    return get_json(
        BACKEND_URL + "/health",
        timeout=2,
    )


def _start_local_backend():
    python_exe = (
        r"C:\MyAgent\.venv\Scripts\python.exe"
    )

    script = (
        r"C:\MyAgent\qingyuan_backend.py"
    )

    creationflags = 0

    if os.name == "nt":
        creationflags = getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0,
        )

    try:
        subprocess.Popen(
            [
                python_exe,
                script,
            ],
            cwd=r"C:\MyAgent",
            shell=False,
            creationflags=creationflags,
        )
        return True
    except Exception as e:
        print(
            f"\n[前端] 后端启动失败：{e}"
        )
        return False


def _backend_matches(status):
    if not isinstance(
        status,
        dict,
    ):
        return False

    return (
        status.get("ok") is True
        and str(
            status.get(
                "version",
                "",
            )
        )
        == QINGYUAN_VERSION
        and int(
            status.get(
                "protocol_version",
                -1,
            )
        )
        == BACKEND_PROTOCOL_VERSION
    )


def _shutdown_existing_backend():
    try:
        post_json(
            BACKEND_URL
            + "/shutdown",
            {},
            timeout=3,
        )
    except Exception:
        pass


def _ensure_backend():
    status = _backend_health()

    if _backend_matches(
        status
    ):
        return status

    if status.get(
        "ok"
    ):
        print(
            "\n[前端] 检测到旧版 Brain Backend："
            f"{status.get('version','unknown')}，"
            f"当前前端：{QINGYUAN_VERSION}。"
        )

        print(
            "[前端] 正在关闭旧 Backend 并加载新版……"
        )

        _shutdown_existing_backend()

        deadline = (
            time.monotonic()
            + 8
        )

        while (
            time.monotonic()
            < deadline
        ):
            time.sleep(
                0.25
            )

            probe = (
                _backend_health()
            )

            if not probe.get(
                "ok"
            ):
                break

    if (
        not AUTO_START_LOCAL_BACKEND
    ):
        return status

    print(
        "\n[前端] 正在启动 "
        f"Brain Backend v{QINGYUAN_VERSION}……"
    )

    if not _start_local_backend():
        return {
            "ok": False,
            "error": (
                "无法启动本机 Brain Backend"
            ),
        }

    deadline = (
        time.monotonic()
        + 30
    )

    last_status = {}

    while (
        time.monotonic()
        < deadline
    ):
        time.sleep(
            0.5
        )

        last_status = (
            _backend_health()
        )

        if _backend_matches(
            last_status
        ):
            return last_status

        if (
            last_status.get(
                "ok"
            )
            and not _backend_matches(
                last_status
            )
        ):
            # 端口仍被旧进程占用，不能假装成功。
            continue

    return {
        "ok": False,
        "error": (
            "Backend 启动后版本握手失败。"
            f"期望 v{QINGYUAN_VERSION} / "
            f"protocol {BACKEND_PROTOCOL_VERSION}，"
            "请检查是否有旧 qingyuan_backend.py 占用 8770。"
        ),
        "backend_status": (
            last_status
        ),
    }


def _start_desktop_pet():
    """启动轻量桌宠表现层。失败不会影响清渊主体。"""
    try:
        python_exe = sys.executable

        if os.name == "nt":
            candidate = os.path.join(
                os.path.dirname(python_exe),
                "pythonw.exe",
            )
            if os.path.isfile(candidate):
                python_exe = candidate

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        return subprocess.Popen(
            [
                python_exe,
                "-m",
                "qingyuan.desktop_pet",
            ],
            cwd=r"C:\MyAgent",
            shell=False,
            creationflags=creationflags,
        )
    except Exception as e:
        print(f"\n[桌宠] 启动失败：{e}")
        return None


def _extract_assistant_reply(result):
    """从 Backend 返回值中提取供桌宠气泡展示的最近回复。"""
    if not isinstance(result, dict):
        return ""

    direct = str(result.get("reply", "")).strip()
    if direct:
        return direct

    logs = str(result.get("logs", ""))
    if not logs:
        return ""

    matches = re.findall(
        r"(?:^|\n)清渊：([^\n]+)",
        logs,
    )

    if not matches:
        return ""

    return str(matches[-1]).strip()


def run():
    WORKSPACE.mkdir(
        parents=True,
        exist_ok=True,
    )

    runtime = RuntimeState()

    temp_cleanup = (
        TempCleanupService(
            runtime.stop_event
        )
    )

    temp_cleanup.start()

    voice = VoiceService(
        runtime
    )

    permission = (
        TaskPermissionBroker(
            runtime,
            voice,
        )
    )

    desktop = (
        DesktopController(
            runtime,
            voice,
            permission,
        )
    )

    vision = VisionService(
        runtime,
        desktop,
        permission,
    )

    desktop.attach_vision(
        vision
    )

    system_tools = (
        SystemTools(
            runtime,
            permission,
        )
    )

    workspace = (
        WorkspaceTools(
            runtime,
            voice,
            desktop
            .enumerate_visible_windows,
        )
    )

    wechat = WeChatTools(
        runtime,
        desktop,
        vision,
    )

    action_host = (
        LocalActionHost(
            runtime,
            voice,
            permission,
            desktop,
            vision,
            workspace,
            system_tools,
            wechat,
        )
    )

    action_thread = (
        threading.Thread(
            target=(
                action_host.start
            ),
            daemon=True,
        )
    )

    action_thread.start()

    # Action Host 必须先起来，
    # 因为 Backend 初始化后可能立即需要前端服务。
    time.sleep(
        0.25
    )

    backend_status = (
        _ensure_backend()
    )

    print(
        "=" * 60
    )
    print(
        f"清渊 Frontend v{QINGYUAN_VERSION} 已启动"
    )
    print(
        r"Windows 前端：C:\MyAgent"
    )
    print(
        "输入方式：键盘 + 麦克风"
    )
    print(
        "唤醒词：清渊"
    )
    print(
        f"连续对话窗口："
        f"{int(ACTIVE_WINDOW_SECONDS)} 秒"
    )
    print(
        "Local Action Host："
        + ACTION_URL
    )
    print(
        "Brain Backend："
        + BACKEND_URL
    )

    if backend_status.get(
        "ok"
    ):
        print(
            "Backend 状态：在线"
        )
        print(
            "Backend 版本："
            + str(
                backend_status.get(
                    "version",
                    "unknown",
                )
            )
        )
        print(
            "模型路由："
            + str(
                backend_status.get(
                    "model_route",
                    "",
                )
            )
        )
        print(
            "本地文档："
            + str(
                backend_status.get(
                    "rag",
                    "",
                )
            )
        )
        print(
            "技能库："
            + str(
                backend_status.get(
                    "skills",
                    0,
                )
            )
            + " 个"
        )
    else:
        print(
            "Backend 状态：离线"
        )
        print(
            "错误："
            + str(
                backend_status.get(
                    "error",
                    "unknown",
                )
            )
        )

    print(
        "权限原则："
        "Brain Backend 不直接拥有 Windows 操作权限"
    )
    print(
        "输入 exit / quit 退出"
    )
    print(
        "=" * 60
    )

    voice.speak(
        "清渊已启动。",
        allow_barge_in=False,
    )

    def standby_worker():
        while not (
            runtime.stop_event
            .is_set()
        ):
            if (
                runtime
                .should_show_sleep_notice()
            ):
                print(
                    "\n🌙 清渊休息啦。"
                )

            time.sleep(
                0.25
            )

    threads = [
        threading.Thread(
            target=start_control_server,
            args=(
                runtime,
                voice,
            ),
            daemon=True,
        ),
        threading.Thread(
            target=voice.keyboard_worker,
            daemon=True,
        ),
        threading.Thread(
            target=voice.voice_worker,
            daemon=True,
        ),
        threading.Thread(
            target=standby_worker,
            daemon=True,
        ),
    ]

    for thread in threads:
        thread.start()

    # 桌宠只是表现层；启动失败不影响 Agent / STT / TTS / Action Host。
    pet_process = _start_desktop_pet()

    try:
        while not (
            runtime.stop_event
            .is_set()
        ):
            try:
                source, user_input = (
                    runtime
                    .input_queue
                    .get(
                        timeout=0.2
                    )
                )
            except queue.Empty:
                continue

            user_input = str(
                user_input
            ).strip()

            if not user_input:
                continue

            runtime.mark_input_received()

            if source != "voice":
                runtime.activate_conversation()

            command = normalize_command(
                user_input
            )

            # ---------------- local frontend controls ----------------

            if command in {
                "voice input on",
                "开启语音输入",
                "打开语音输入",
                "语音输入开启",
                "恢复监听",
                "开始监听",
            }:
                runtime.voice_listen_enabled = True
                print(
                    "\n清渊：麦克风监听已经开启。"
                )
                voice.speak(
                    "麦克风监听已经开启。",
                    allow_barge_in=False,
                )
                runtime.activate_conversation()
                continue

            if command in {
                "voice input off",
                "关闭语音输入",
                "关掉语音输入",
                "语音输入关闭",
                "停止语音输入",
                "停止监听",
                "别听了",
            }:
                runtime.voice_listen_enabled = False
                voice.cancel_listen()
                runtime.go_standby()
                print(
                    "\n清渊：麦克风监听已经关闭，"
                    "键盘仍然可用。"
                )
                voice.speak(
                    "麦克风监听已经关闭。",
                    allow_barge_in=False,
                )
                continue

            if command in {
                "voice on",
                "开启语音",
                "打开语音",
                "语音开启",
            }:
                runtime.voice_enabled = True
                print(
                    "\n清渊：语音输出已经开启。"
                )
                voice.speak(
                    "语音输出已经开启。",
                    allow_barge_in=False,
                )
                continue

            if command in {
                "voice off",
                "关闭语音",
                "关掉语音",
                "语音关闭",
            }:
                voice.stop_speaking()
                runtime.voice_enabled = False
                print(
                    "\n清渊：语音输出已经关闭。"
                )
                continue

            if is_standby_phrase(
                user_input
            ):
                voice.stop_speaking()
                runtime.go_standby()
                print(
                    "\n清渊：好。"
                )
                voice.speak(
                    "好。",
                    allow_barge_in=False,
                )
                continue

            if command in {
                "exit",
                "quit",
                "退出清渊",
                "关闭清渊",
            }:
                print(
                    "\n清渊：下次见。"
                )

                voice.stop_speaking()
                runtime.stop_event.set()
                voice.cancel_listen()
                break

            # ---------------- send normal command to backend ----------------

            if source == "voice":
                print(
                    f"\n你（语音）："
                    f"{user_input}"
                )

            # Backend 命令异步执行。
            # Frontend 主循环必须保持可响应，
            # 这样执行期间用户仍能输入：
            # 取消 / 停止 / 结束任务 / 别做了
            runtime.agent_busy.set()
            voice.cancel_listen()

            command_done = threading.Event()
            command_result = {}

            def backend_command_worker():
                try:
                    result = post_json(
                        BACKEND_URL
                        + "/command",
                        {
                            "source": source,
                            "text": user_input,
                        },
                        timeout=3600,
                    )

                    command_result[
                        "result"
                    ] = result

                except Exception as e:
                    command_result[
                        "result"
                    ] = {
                        "ok": False,
                        "error": str(e),
                    }

                finally:
                    command_done.set()

            worker = threading.Thread(
                target=backend_command_worker,
                name="qingyuan-backend-command",
                daemon=True,
            )

            worker.start()

            cancel_commands = {
                "取消",
                "取消任务",
                "停止",
                "停止任务",
                "结束任务",
                "终止任务",
                "中止任务",
                "别做了",
                "别弄了",
                "停下来",
                "stop",
                "cancel",
                "cancel task",
                "stop task",
            }

            # 等 Backend 的同时继续消费“紧急控制”输入。
            while (
                not command_done.is_set()
                and not runtime.stop_event.is_set()
            ):
                try:
                    urgent_source, urgent_text = (
                        runtime
                        .input_queue
                        .get(
                            timeout=0.15
                        )
                    )
                except queue.Empty:
                    continue

                urgent_text = str(
                    urgent_text
                ).strip()

                urgent_command = (
                    normalize_command(
                        urgent_text
                    )
                )

                if (
                    urgent_command
                    in cancel_commands
                ):
                    print(
                        f"\n你（{urgent_source}）："
                        f"{urgent_text}"
                    )

                    print(
                        "\n[紧急停止] "
                        "正在取消当前任务并收回权限……"
                    )

                    # Backend cancel
                    try:
                        post_json(
                            BACKEND_URL
                            + "/cancel",
                            {},
                            timeout=5,
                        )
                    except Exception:
                        pass

                    # Action Host 再兜底一次。
                    try:
                        post_json(
                            ACTION_URL
                            + "/cancel",
                            {},
                            timeout=5,
                        )
                    except Exception:
                        pass

                    try:
                        runtime.request_task_cancel()
                    except Exception:
                        try:
                            runtime.cancel_event.set()
                        except Exception:
                            pass

                    voice.stop_speaking()
                    voice.cancel_listen()

                    print(
                        "清渊：当前任务已取消。"
                    )

                    voice.speak(
                        "当前任务已取消。",
                        allow_barge_in=False,
                    )

                    # 不需要等很久。
                    command_done.wait(
                        timeout=5
                    )

                    break

                # 执行期间普通新命令不能偷偷叠加成并发任务。
                # 放回队列末尾，等当前任务完成。
                runtime.input_queue.put(
                    (
                        urgent_source,
                        urgent_text,
                    )
                )

                time.sleep(
                    0.05
                )

            result = command_result.get(
                "result",
                {
                    "ok": False,
                    "error": (
                        "Backend command interrupted"
                    ),
                },
            )

            runtime.agent_busy.clear()

            if not result.get(
                "ok"
            ):
                # 如果是用户主动取消，不再打印为 Backend 错误。
                try:
                    cancelled = (
                        runtime.task_cancelled()
                    )
                except Exception:
                    cancelled = False

                if not cancelled:
                    print(
                        "\n【Backend 错误】"
                    )
                    print(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )

                continue

            semantic = (
                result.get(
                    "semantic"
                )
            )

            if (
                source == "voice"
                and isinstance(
                    semantic,
                    dict,
                )
                and semantic.get(
                    "changed"
                )
            ):
                print(
                    "[语义纠正] "
                    f"{user_input}"
                    "  →  "
                    f"{semantic.get('text','')}"
                    "  "
                    f"(置信度 "
                    f"{float(semantic.get('confidence',0)):.2f})"
                )

            logs = str(
                result.get(
                    "logs",
                    "",
                )
            ).strip()

            if logs:
                print(
                    logs
                )

            pet_reply = _extract_assistant_reply(
                result
            )
            if pet_reply:
                runtime.set_last_assistant_text(
                    pet_reply
                )

            runtime.activate_conversation()

    except KeyboardInterrupt:
        runtime.stop_event.set()

    finally:
        if (
            pet_process is not None
            and pet_process.poll() is None
        ):
            try:
                pet_process.terminate()
            except Exception:
                pass

        if (
            AUTO_SHUTDOWN_LOCAL_BACKEND
        ):
            try:
                post_json(
                    BACKEND_URL
                    + "/shutdown",
                    {},
                    timeout=3,
                )
            except Exception:
                pass

        voice.shutdown_voice_services()
