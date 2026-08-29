import json
import threading
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from .ipc_auth import get_ipc_token
from .ipc_config import (
    ACTION_HOST,
    ACTION_PORT,
)


class LocalActionHost:
    """
    Windows 端真实动作宿主。

    Brain Backend 只能通过这里调用：
    - Task Permit
    - Windows / mouse / keyboard
    - Vision desktop tools
    - Filesystem tools
    - WeChat tools

    最终权限强制仍在 Windows 前端。
    """

    def __init__(
        self,
        runtime,
        voice,
        permission,
        desktop,
        vision,
        workspace,
        system_tools,
        wechat,
    ):
        self.runtime = runtime
        self.voice = voice
        self.permission = permission
        self.desktop = desktop
        self.vision = vision
        self.workspace = workspace
        self.system = system_tools
        self.wechat = wechat
        self.server = None

    def registry(self):
        return {
            # task request
            "begin_request":
                self.permission.begin_request,

            # task permit
            "authorize_task":
                self.permission.authorize_task,
            "end_task":
                self.permission.end_task,

            # desktop permit
            "authorize_desktop_task":
                self.desktop.authorize_desktop_task,
            "end_desktop_task":
                self.desktop.end_desktop_task,
            "desktop_task_status":
                self.desktop.desktop_task_status,

            # desktop
            "list_open_windows":
                self.desktop.list_open_windows,
            "focus_window":
                self.desktop.focus_window,
            "bring_app_to_foreground":
                self.desktop.bring_app_to_foreground,
            "mouse_click":
                self.desktop.mouse_click,
            "keyboard_type":
                self.desktop.keyboard_type,
            "press_key":
                self.desktop.press_key,
            "keyboard_shortcut":
                self.desktop.keyboard_shortcut,
            "browser_search_new_tab":
                self.desktop.browser_search_new_tab,
            "scroll":
                self.desktop.scroll,

            # vision
            "capture_screen":
                self.vision.capture_screen,
            "analyze_screen":
                self.vision.analyze_screen,
            "locate_screen_element":
                self.vision.locate_screen_element,
            "click_screen_element":
                self.vision.click_screen_element,

            # filesystem
            "list_path":
                self.system.list_path,
            "read_text_file":
                self.system.read_text_file,
            "write_text_file":
                self.system.write_text_file,
            "create_folder":
                self.system.create_folder,
            "move_path":
                self.system.move_path,
            "delete_path":
                self.system.delete_path,
            "open_path":
                self.system.open_path,
            "launch_program":
                self.system.launch_program,

            # read-only system info
            "get_current_time":
                self.system.get_current_time,

            # guarded coding agent
            "code_begin_session":
                self.system.code_begin_session,
            "code_session_status":
                self.system.code_session_status,
            "code_project_tree":
                self.system.code_project_tree,
            "code_read_file":
                self.system.code_read_file,
            "code_write_file":
                self.system.code_write_file,
            "code_git_status":
                self.system.code_git_status,
            "code_git_diff":
                self.system.code_git_diff,
            "code_run_checks":
                self.system.code_run_checks,
            "code_rollback":
                self.system.code_rollback,
            "code_finish_session":
                self.system.code_finish_session,

            # system power/session
            "system_power":
                self.system.system_power,

            # workspace
            "list_files":
                self.workspace.list_files,
            "read_file":
                self.workspace.read_file,
            "open_app":
                self.workspace.open_app,

            # app
            "wechat_send_message":
                self.wechat.wechat_send_message,
        }

    def _status(self):
        return {
            "ok": True,
            "service": "qingyuan-action-host",
            "desktop_task_active": (
                self.runtime
                .desktop_task_is_active()
            ),
            "action_types": list(
                self.runtime
                .desktop_action_types()
            ),
            "voice_enabled": bool(
                self.runtime.voice_enabled
            ),
            "mic_enabled": bool(
                self.runtime
                .voice_listen_enabled
            ),
        }

    def emergency_cancel(self):
        """
        Windows 侧立即中止当前任务。

        这里是最终安全边界：
        - 标记 cancel_event
        - 停止说话/监听
        - 尝试收回 desktop task
        - 尝试收回 generic task permit
        """
        try:
            self.runtime.request_task_cancel()
        except Exception:
            try:
                self.runtime.cancel_event.set()
            except Exception:
                pass

        try:
            self.voice.stop_speaking()
        except Exception:
            pass

        try:
            self.voice.cancel_listen()
        except Exception:
            pass

        results = []

        try:
            result = (
                self.desktop
                .end_desktop_task()
            )
            results.append(
                str(result)
            )
        except Exception as e:
            results.append(
                f"desktop revoke: {e}"
            )

        try:
            result = (
                self.permission
                .end_task()
            )
            results.append(
                str(result)
            )
        except Exception as e:
            results.append(
                f"permit revoke: {e}"
            )

        try:
            self.runtime.clear_desktop_task(
                preserve_request=False
            )
        except Exception:
            pass

        return {
            "cancelled": True,
            "revoke_results": results,
        }

    def start(self):
        host = self

        class Handler(
            BaseHTTPRequestHandler
        ):
            def _authorized(self):
                return (
                    self.headers.get(
                        "X-Qingyuan-Token",
                        "",
                    )
                    == get_ipc_token()
                )

            def _send(
                self,
                code,
                data,
            ):
                payload = json.dumps(
                    data,
                    ensure_ascii=False,
                ).encode("utf-8")

                self.send_response(
                    code
                )

                self.send_header(
                    "Content-Type",
                    (
                        "application/json; "
                        "charset=utf-8"
                    ),
                )

                self.send_header(
                    "Content-Length",
                    str(len(payload)),
                )

                self.end_headers()

                try:
                    self.wfile.write(
                        payload
                    )
                except Exception:
                    pass

            def _read_json(self):
                length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                    or 0
                )

                raw = self.rfile.read(
                    length
                )

                if not raw:
                    return {}

                try:
                    data = json.loads(
                        raw.decode(
                            "utf-8"
                        )
                    )

                    return (
                        data
                        if isinstance(
                            data,
                            dict,
                        )
                        else {}
                    )
                except Exception:
                    return {}

            def do_GET(self):
                if not self._authorized():
                    self._send(
                        403,
                        {
                            "ok": False,
                            "error": "unauthorized",
                        },
                    )
                    return

                path = self.path.split(
                    "?",
                    1,
                )[0]

                if path in {
                    "/health",
                    "/status",
                }:
                    self._send(
                        200,
                        host._status(),
                    )
                    return

                self._send(
                    404,
                    {
                        "ok": False,
                        "error": "not found",
                    },
                )

            def do_POST(self):
                if not self._authorized():
                    self._send(
                        403,
                        {
                            "ok": False,
                            "error": "unauthorized",
                        },
                    )
                    return

                path = self.path.split(
                    "?",
                    1,
                )[0]

                data = self._read_json()

                if path == "/tool":
                    name = str(
                        data.get(
                            "name",
                            "",
                        )
                    ).strip()

                    args = data.get(
                        "args",
                        {},
                    )

                    if not isinstance(
                        args,
                        dict,
                    ):
                        args = {}

                    fn = host.registry().get(
                        name
                    )

                    if fn is None:
                        self._send(
                            404,
                            {
                                "ok": False,
                                "error": (
                                    f"unknown tool: {name}"
                                ),
                            },
                        )
                        return

                    try:
                        result = fn(
                            **args
                        )

                        self._send(
                            200,
                            {
                                "ok": True,
                                "result": result,
                                "status": (
                                    host._status()
                                ),
                            },
                        )

                    except Exception as e:
                        self._send(
                            500,
                            {
                                "ok": False,
                                "error": (
                                    f"{type(e).__name__}: {e}"
                                ),
                            },
                        )

                    return

                if path == "/cancel":
                    result = (
                        host.emergency_cancel()
                    )

                    self._send(
                        200,
                        {
                            "ok": True,
                            "result": result,
                            "status": (
                                host._status()
                            ),
                        },
                    )
                    return

                if path == "/speak":
                    text = str(
                        data.get(
                            "text",
                            "",
                        )
                    )

                    allow_barge_in = bool(
                        data.get(
                            "allow_barge_in",
                            True,
                        )
                    )

                    try:
                        result = (
                            host.voice.speak(
                                text,
                                allow_barge_in=(
                                    allow_barge_in
                                ),
                            )
                        )

                        self._send(
                            200,
                            {
                                "ok": True,
                                "result": result,
                            },
                        )

                    except Exception as e:
                        self._send(
                            500,
                            {
                                "ok": False,
                                "error": str(e),
                            },
                        )

                    return

                if path == "/stop-speaking":
                    host.voice.stop_speaking()

                    self._send(
                        200,
                        {"ok": True},
                    )
                    return

                if path == "/confirm":
                    prompt = str(
                        data.get(
                            "prompt",
                            "",
                        )
                    )

                    operation_name = str(
                        data.get(
                            "operation_name",
                            "执行操作",
                        )
                    )

                    result = (
                        host.voice
                        .request_confirmation(
                            prompt,
                            operation_name=(
                                operation_name
                            ),
                        )
                    )

                    self._send(
                        200,
                        {
                            "ok": True,
                            "confirmed": bool(
                                result
                            ),
                        },
                    )
                    return

                self._send(
                    404,
                    {
                        "ok": False,
                        "error": "not found",
                    },
                )

            def log_message(
                self,
                format,
                *args,
            ):
                return

        self.server = ThreadingHTTPServer(
            (
                ACTION_HOST,
                ACTION_PORT,
            ),
            Handler,
        )

        self.server.timeout = 0.5

        print(
            "[前端] Local Action Host："
            f"http://{ACTION_HOST}:{ACTION_PORT}"
        )

        try:
            while not (
                self.runtime
                .stop_event
                .is_set()
            ):
                self.server.handle_request()
        finally:
            self.server.server_close()
