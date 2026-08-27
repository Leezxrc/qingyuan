class ToolFactory:
    """
    Factory 只负责“当前任务给模型哪些工具”。

    权限本身由 TaskPermissionBroker 强制执行，
    所以模型看到工具 ≠ 模型自动有权限。
    """

    def __init__(
        self,
        desktop,
        vision,
        workspace,
        memory,
        wechat,
        permission,
        system_tools,
    ):
        self.desktop = desktop
        self.vision = vision
        self.workspace = workspace
        self.memory = memory
        self.wechat = wechat
        self.permission = permission
        self.system = system_tools

    def _registry(self):
        return {
            # task permit
            "authorize_task": self.permission.authorize_task,
            "end_task": self.permission.end_task,

            # compatibility / desktop
            "authorize_desktop_task": self.desktop.authorize_desktop_task,
            "end_desktop_task": self.desktop.end_desktop_task,
            "desktop_task_status": self.desktop.desktop_task_status,

            # windows / desktop
            "list_open_windows": self.desktop.list_open_windows,
            "focus_window": self.desktop.focus_window,
            "bring_app_to_foreground": self.desktop.bring_app_to_foreground,
            "mouse_click": self.desktop.mouse_click,
            "keyboard_type": self.desktop.keyboard_type,
            "press_key": self.desktop.press_key,
            "keyboard_shortcut": self.desktop.keyboard_shortcut,
            "browser_search_new_tab": self.desktop.browser_search_new_tab,
            "scroll": self.desktop.scroll,

            # vision
            "capture_screen": self.vision.capture_screen,
            "analyze_screen": self.vision.analyze_screen,
            "locate_screen_element": self.vision.locate_screen_element,
            "click_screen_element": self.vision.click_screen_element,

            # broad structured OS/file tools
            "list_path": self.system.list_path,
            "read_text_file": self.system.read_text_file,
            "write_text_file": self.system.write_text_file,
            "create_folder": self.system.create_folder,
            "move_path": self.system.move_path,
            "delete_path": self.system.delete_path,
            "open_path": self.system.open_path,
            "launch_program": self.system.launch_program,

            # system info
            "get_current_time": self.system.get_current_time,

            # system power/session
            "system_power": self.system.system_power,

            # old workspace helpers
            "list_files": self.workspace.list_files,
            "read_file": self.workspace.read_file,

            # apps
            "open_app": self.workspace.open_app,

            # WeChat
            "wechat_send_message": self.wechat.wechat_send_message,

            # memory
            "remember_memory": self.memory.remember_memory,
            "list_memories": self.memory.list_memories,
            "forget_memory": self.memory.forget_memory,
        }

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
        ],
    }

    def create(self, intent):
        registry = self._registry()
        names = self.TOOLSETS.get(intent, [])

        tools = [
            registry[name]
            for name in names
        ]

        available = {
            name: registry[name]
            for name in names
        }

        return tools, available