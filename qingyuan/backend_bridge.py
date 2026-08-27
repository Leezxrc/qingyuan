from .ipc_config import ACTION_URL
from .ipc_http import (
    get_json,
    post_json,
)


class RemoteVoiceProxy:
    """
    Brain Backend 不直接接触麦克风/音箱。
    所有声音与确认都交给 Windows 前端。
    """

    def __init__(
        self,
        runtime,
    ):
        self.runtime = runtime

    def speak(
        self,
        text,
        allow_barge_in=True,
    ):
        if not self.runtime.voice_enabled:
            return None

        return post_json(
            ACTION_URL + "/speak",
            {
                "text": str(text),
                "allow_barge_in": bool(
                    allow_barge_in
                ),
            },
            timeout=3600,
        )

    def stop_speaking(self):
        return post_json(
            ACTION_URL
            + "/stop-speaking",
            {},
            timeout=10,
        )

    def request_confirmation(
        self,
        prompt,
        operation_name="执行操作",
    ):
        response = post_json(
            ACTION_URL + "/confirm",
            {
                "prompt": str(prompt),
                "operation_name": (
                    str(operation_name)
                ),
            },
            timeout=120,
        )

        return bool(
            response.get(
                "confirmed",
                False,
            )
        )

    def cancel_listen(self):
        return None


class RemotePermissionProxy:
    """
    Agent Core 用到的 permission facade。

    真正的许可证仍由 Windows Action Host
    中的 TaskPermissionBroker 创建。
    """

    def __init__(
        self,
        runtime,
    ):
        self.runtime = runtime
        self._original_request = ""

    @staticmethod
    def _tool(
        name,
        **args,
    ):
        response = post_json(
            ACTION_URL + "/tool",
            {
                "name": name,
                "args": args,
            },
            timeout=3600,
        )

        if not response.get(
            "ok"
        ):
            return (
                "前端动作宿主调用失败："
                + str(
                    response.get(
                        "error",
                        "unknown error",
                    )
                )
            )

        return response.get(
            "result"
        )

    def begin_request(
        self,
        user_request,
    ):
        self._original_request = (
            str(user_request).strip()
        )

        return self._tool(
            "begin_request",
            user_request=(
                self._original_request
            ),
        )

    def authorize_task(
        self,
        capabilities: list,
        targets: list = None,
    ):
        result = self._tool(
            "authorize_task",
            capabilities=capabilities,
            targets=targets,
        )

        if (
            isinstance(result, str)
            and result.startswith(
                "任务许可证已生效"
            )
        ):
            with self.runtime.desktop_lock:
                self.runtime.desktop_task[
                    "active"
                ] = True

        return result

    def end_task(self):
        result = self._tool(
            "end_task"
        )

        self.runtime.clear_desktop_task(
            preserve_request=True
        )

        return result


class RemoteToolFactory:
    """
    Brain Backend 的工具全部是“代理函数”。

    模型能看到工具 schema，
    但真实 Windows 操作必须通过
    Local Action Host。
    """

    def __init__(
        self,
        runtime,
        memory,
    ):
        self.runtime = runtime
        self.memory = memory
        self.permission = (
            RemotePermissionProxy(
                runtime
            )
        )

    def _call(
        self,
        name,
        **args,
    ):
        try:
            if self.runtime.task_cancelled():
                return "任务已取消：未调用前端工具。"
        except Exception:
            pass

        response = post_json(
            ACTION_URL + "/tool",
            {
                "name": name,
                "args": args,
            },
            timeout=3600,
        )

        status = response.get(
            "status",
            {}
        )

        if isinstance(
            status,
            dict,
        ):
            active = bool(
                status.get(
                    "desktop_task_active",
                    False,
                )
            )

            with self.runtime.desktop_lock:
                self.runtime.desktop_task[
                    "active"
                ] = active

                for action in status.get(
                    "action_types",
                    [],
                ):
                    self.runtime.desktop_task[
                        "action_types"
                    ].add(
                        str(action)
                    )

        if not response.get(
            "ok"
        ):
            return (
                "前端动作宿主调用失败："
                + str(
                    response.get(
                        "error",
                        "unknown error",
                    )
                )
            )

        return response.get(
            "result"
        )

    # ---------- permit ----------

    def authorize_task(
        self,
        capabilities: list,
        targets: list = None,
    ):
        """申请本次用户任务所需的临时能力许可证。"""
        return (
            self.permission
            .authorize_task(
                capabilities,
                targets,
            )
        )

    def end_task(self):
        """结束当前任务并立即收回权限。"""
        return (
            self.permission.end_task()
        )

    def authorize_desktop_task(
        self,
        task_description: str,
        target_window_keyword: str,
        capabilities: list,
    ):
        """绑定并授权本次指定桌面窗口任务。"""
        result = self._call(
            "authorize_desktop_task",
            task_description=(
                task_description
            ),
            target_window_keyword=(
                target_window_keyword
            ),
            capabilities=capabilities,
        )

        if (
            isinstance(result, str)
            and "授权" in result
            and "拒绝" not in result
            and "没有找到" not in result
        ):
            with self.runtime.desktop_lock:
                self.runtime.desktop_task[
                    "active"
                ] = True

        return result

    def end_desktop_task(self):
        """结束桌面任务并收回本次桌面权限。"""
        result = self._call(
            "end_desktop_task"
        )

        self.runtime.clear_desktop_task(
            preserve_request=True
        )

        return result

    def desktop_task_status(self):
        """读取当前桌面任务状态。"""
        return self._call(
            "desktop_task_status"
        )

    # ---------- desktop ----------

    def list_open_windows(self):
        """列出当前任务允许读取的可见窗口。"""
        return self._call(
            "list_open_windows"
        )

    def focus_window(
        self,
        title_keyword: str,
    ):
        """聚焦当前任务允许控制的指定窗口。"""
        return self._call(
            "focus_window",
            title_keyword=title_keyword,
        )

    def bring_app_to_foreground(
        self,
        title_keyword: str,
    ):
        """把用户指定并已授权的应用窗口切换到前台。"""
        return self._call(
            "bring_app_to_foreground",
            title_keyword=title_keyword,
        )

    def mouse_click(
        self,
        x: int,
        y: int,
        button: str = "left",
    ):
        """在已授权窗口内点击屏幕坐标。"""
        return self._call(
            "mouse_click",
            x=x,
            y=y,
            button=button,
        )

    def keyboard_type(
        self,
        text_to_type: str,
    ):
        """向已授权窗口输入用户任务所需文本。"""
        return self._call(
            "keyboard_type",
            text_to_type=text_to_type,
        )

    def press_key(
        self,
        key: str,
    ):
        """在已授权窗口按下指定按键。"""
        return self._call(
            "press_key",
            key=key,
        )

    def keyboard_shortcut(
        self,
        keys: list,
    ):
        """在已授权窗口执行指定键盘快捷键。"""
        return self._call(
            "keyboard_shortcut",
            keys=keys,
        )

    def browser_search_new_tab(
        self,
        query: str,
    ):
        """在已授权浏览器新标签页搜索指定内容。"""
        return self._call(
            "browser_search_new_tab",
            query=query,
        )

    def scroll(
        self,
        amount: int,
    ):
        """在已授权窗口滚动指定距离。"""
        return self._call(
            "scroll",
            amount=amount,
        )

    # ---------- vision ----------

    def capture_screen(self):
        """截取当前已授权窗口/屏幕供任务判断。"""
        return self._call(
            "capture_screen"
        )

    def analyze_screen(
        self,
        question: str,
    ):
        """分析当前已授权屏幕内容并回答任务相关问题。"""
        return self._call(
            "analyze_screen",
            question=question,
        )

    def locate_screen_element(
        self,
        description: str,
    ):
        """定位当前授权界面中指定元素。"""
        return self._call(
            "locate_screen_element",
            description=description,
        )

    def click_screen_element(
        self,
        description: str,
        button: str = "left",
    ):
        """定位并点击当前授权界面中的指定元素。"""
        return self._call(
            "click_screen_element",
            description=description,
            button=button,
        )

    # ---------- read-only system info ----------

    def get_current_time(self):
        """
        读取 Windows Action Host 返回的当前本机日期、星期和时间。
        这是低风险只读系统信息，不需要 Task Permit。
        """
        return self._call(
            "get_current_time"
        )

    # ---------- system power/session ----------

    def system_power(
        self,
        action: str,
    ):
        """
        执行固定白名单 Windows 电源/会话动作。

        action:
        shutdown / restart / sleep / lock / logout
        """
        return self._call(
            "system_power",
            action=action,
        )

    # ---------- filesystem ----------

    def list_path(
        self,
        path: str,
    ):
        """列出用户任务授权路径内容。"""
        return self._call(
            "list_path",
            path=path,
        )

    def read_text_file(
        self,
        path: str,
    ):
        """读取用户任务授权的文本文件。"""
        return self._call(
            "read_text_file",
            path=path,
        )

    def write_text_file(
        self,
        path: str,
        content: str,
    ):
        """写入用户任务授权的文本文件。"""
        return self._call(
            "write_text_file",
            path=path,
            content=content,
        )

    def create_folder(
        self,
        path: str,
    ):
        """创建用户任务授权的文件夹。"""
        return self._call(
            "create_folder",
            path=path,
        )

    def move_path(
        self,
        source: str,
        destination: str,
    ):
        """移动或重命名用户任务授权的文件/目录。"""
        return self._call(
            "move_path",
            source=source,
            destination=destination,
        )

    def delete_path(
        self,
        path: str,
    ):
        """删除用户明确要求且已授权的文件/目录。"""
        return self._call(
            "delete_path",
            path=path,
        )

    def open_path(
        self,
        path: str,
    ):
        """打开用户明确指定并已授权的路径。"""
        return self._call(
            "open_path",
            path=path,
        )

    def launch_program(
        self,
        program: str,
        arguments: list = None,
    ):
        """启动用户明确指定且允许启动的程序。"""
        return self._call(
            "launch_program",
            program=program,
            arguments=arguments,
        )

    # ---------- compatibility ----------

    def list_files(self):
        """列出清渊 workspace 文件。"""
        return self._call(
            "list_files"
        )

    def read_file(
        self,
        relative_path: str,
    ):
        """读取清渊 workspace 文本文件。"""
        return self._call(
            "read_file",
            relative_path=relative_path,
        )

    def open_app(
        self,
        app_name: str,
    ):
        """兼容方式打开指定白名单应用。"""
        return self._call(
            "open_app",
            app_name=app_name,
        )

    # ---------- WeChat ----------

    def wechat_send_message(
        self,
        chat_identifier: str,
        message: str,
    ):
        """向用户指定且已授权的微信聊天发送指定消息。"""
        return self._call(
            "wechat_send_message",
            chat_identifier=(
                chat_identifier
            ),
            message=message,
        )

    # ---------- local brain memory ----------

    def remember_memory(
        self,
        content: str,
    ):
        """保存用户明确要求记住的一条长期记忆。"""
        return (
            self.memory
            .remember_memory(
                content
            )
        )

    def list_memories(self):
        """列出当前长期记忆。"""
        return (
            self.memory
            .list_memories()
        )

    def forget_memory(
        self,
        keyword: str,
    ):
        """删除包含指定关键词的长期记忆。"""
        return (
            self.memory
            .forget_memory(
                keyword
            )
        )

    TOOLSETS = {
        "chat": [],

        # low-risk read-only system information
        "system_info": [
            "get_current_time",
        ],

        "memory": [
            "remember_memory",
            "list_memories",
            "forget_memory",
        ],

        "filesystem": [
            "authorize_task",
            "list_path",
            "read_text_file",
            "write_text_file",
            "create_folder",
            "move_path",
            "delete_path",
            "open_path",
            "end_task",
        ],

        "app_launch": [
            "authorize_task",
            "launch_program",
            "list_open_windows",
            "end_task",
        ],

        "system_power": [
            "authorize_task",
            "system_power",
            "end_task",
        ],

        "foreground": [
            "authorize_desktop_task",
            "bring_app_to_foreground",
            "end_desktop_task",
        ],

        "browser_search": [
            "authorize_desktop_task",
            "browser_search_new_tab",
            "end_desktop_task",
        ],

        "wechat_send": [
            "authorize_desktop_task",
            "wechat_send_message",
            "end_desktop_task",
        ],

        "gui": [
            "authorize_desktop_task",
            "authorize_task",
            "list_open_windows",
            "bring_app_to_foreground",
            "analyze_screen",
            "capture_screen",
            "locate_screen_element",
            "click_screen_element",
            "mouse_click",
            "keyboard_type",
            "press_key",
            "keyboard_shortcut",
            "scroll",
            "launch_program",
            "open_path",
            "end_task",
            "end_desktop_task",
        ],
    }

    def _registry(self):
        return {
            name: getattr(
                self,
                name,
            )
            for name in {
                item
                for items in (
                    self.TOOLSETS.values()
                )
                for item in items
            }
        }

    def create(
        self,
        intent,
    ):
        registry = (
            self._registry()
        )

        names = (
            self.TOOLSETS.get(
                intent,
                [],
            )
        )

        tools = [
            registry[name]
            for name in names
        ]

        available = {
            name: registry[name]
            for name in names
        }

        return tools, available
