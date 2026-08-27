import ctypes
import json
import time
from ctypes import wintypes

from .config import (
    DESKTOP_CAPABILITIES,
    PERSISTENT_SCREEN_ACCESS,
)


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

try:
    user32.SetProcessDPIAware()
except Exception:
    pass

SW_RESTORE = 9
SW_SHOW = 5

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WHEEL_DELTA = 120

VK_CODES = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08,
    "delete": 0x2E, "home": 0x24, "end": 0x23,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "space": 0x20, "f4": 0x73,
    "l": 0x4C, "a": 0x41, "c": 0x43, "v": 0x56, "x": 0x58,
    "t": 0x54,
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


class DesktopController:
    def __init__(self, runtime, voice, permission):
        self.runtime = runtime
        self.voice = voice
        self.permission = permission
        self.vision = None

    def attach_vision(self, vision):
        self.vision = vision

    # ---------------- windows ----------------

    @staticmethod
    def _get_window_title(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value.strip()

    def enumerate_visible_windows(self):
        windows = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = self._get_window_title(hwnd)
            if title:
                windows.append({"hwnd": int(hwnd), "title": title})
            return True

        user32.EnumWindows(callback, 0)
        return windows

    def list_open_windows(self) -> str:
        """列出当前任务已授权的可见顶层窗口标题。"""
        ok, reason = self.permission.require("window_read")
        if not ok:
            return reason

        windows = self.enumerate_visible_windows()
        if not windows:
            return "当前没有发现可见窗口。"
        return "\n".join(
            f"- {item['title']}" for item in windows
        )

    def _find_window(self, keyword):
        keyword = str(keyword).strip().lower()
        matches = [
            item for item in self.enumerate_visible_windows()
            if keyword in item["title"].lower()
        ]
        if not matches:
            return None
        matches.sort(key=lambda x: len(x["title"]))
        return matches[0]

    def _force_foreground(self, hwnd):
        hwnd = int(hwnd)
        if not user32.IsWindow(hwnd):
            return False

        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.12)

        if int(user32.GetForegroundWindow()) == hwnd:
            return True

        current_fg = user32.GetForegroundWindow()
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        fg_thread = (
            user32.GetWindowThreadProcessId(current_fg, None)
            if current_fg else 0
        )

        attached_target = False
        attached_fg = False
        try:
            if target_thread and target_thread != current_thread:
                attached_target = bool(
                    user32.AttachThreadInput(
                        current_thread, target_thread, True
                    )
                )
            if (
                fg_thread
                and fg_thread != current_thread
                and fg_thread != target_thread
            ):
                attached_fg = bool(
                    user32.AttachThreadInput(
                        current_thread, fg_thread, True
                    )
                )

            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            if attached_fg:
                user32.AttachThreadInput(
                    current_thread, fg_thread, False
                )
            if attached_target:
                user32.AttachThreadInput(
                    current_thread, target_thread, False
                )

        time.sleep(0.15)
        return int(user32.GetForegroundWindow()) == hwnd

    def desktop_target_ok(self):
        if not self.runtime.desktop_task_is_active():
            return False
        with self.runtime.desktop_lock:
            target = self.runtime.desktop_task["target_hwnd"]
        return int(user32.GetForegroundWindow()) == int(target or 0)

    # ---------------- authorization ----------------

    def authorize_desktop_task(
        self,
        task_description: str,
        target_window_keyword: str,
        capabilities: list,
    ) -> str:
        """
        兼容旧调用的桌面任务授权包装器。

        task_description 参数不会作为真正授权依据；
        授权显示的任务永远是用户原始命令。
        """
        mapping = {
            "screen": "screen_read",
            "screen_read": "screen_read",
            "focus": "window_control",
            "window_control": "window_control",
            "mouse": "mouse",
            "keyboard": "keyboard",
            "scroll": "scroll",
            "window_read": "window_read",
        }

        requested = []
        for item in capabilities or []:
            key = str(item).strip().lower()
            requested.append(
                mapping.get(key, key)
            )

        if "window_read" not in requested:
            requested.append("window_read")

        targets = []
        keyword = str(target_window_keyword).strip()
        if keyword:
            targets.append(keyword)

        result = self.permission.authorize_task(
            capabilities=requested,
            targets=targets,
        )

        if not result.startswith(
            "任务许可证已生效"
        ):
            return result

        # 授权后查找并绑定目标窗口。
        target = self._find_window(keyword)
        if not target:
            self.runtime.clear_desktop_task(
                preserve_request=True
            )
            return (
                "任务已经授权，但没有找到目标窗口："
                f"{target_window_keyword}。权限已收回。"
            )

        with self.runtime.desktop_lock:
            self.runtime.desktop_task[
                "target_hwnd"
            ] = target["hwnd"]
            self.runtime.desktop_task[
                "target_title"
            ] = target["title"]

        if self.permission.has(
            "window_control"
        ):
            if not self._force_foreground(
                target["hwnd"]
            ):
                self.runtime.clear_desktop_task(
                    preserve_request=True
                )
                return (
                    "Windows 未能把目标窗口切到前台，"
                    "任务权限已收回。"
                )

            self.runtime.record_desktop_action(
                "focus_window"
            )

        return result + f"；已绑定窗口：{target['title']}"

    def desktop_task_status(self) -> str:
        """查看当前桌面任务授权状态。"""
        if not self.runtime.desktop_task_is_active():
            return "当前没有有效桌面任务授权。"
        with self.runtime.desktop_lock:
            task = dict(self.runtime.desktop_task)
        return (
            f"任务：{task['description']}\n"
            f"目标：{task['target_title']}\n"
            f"权限：{sorted(task['capabilities'])}\n"
            f"动作：{sorted(task['action_types'])}"
        )

    def end_desktop_task(self) -> str:
        """结束当前任务并收回全部临时权限。"""
        return self.permission.end_task()

    # ---------------- focus ----------------

    def focus_window(self, title_keyword: str) -> str:
        """把当前任务目标窗口真实切到前台并验证。"""
        if not self.permission.has("window_control"):
            return "当前任务没有 window_control 权限。"

        target = self._find_window(title_keyword)
        if not target:
            return f"没有找到标题包含“{title_keyword}”的窗口。"

        with self.runtime.desktop_lock:
            expected = self.runtime.desktop_task["target_hwnd"]
        if int(target["hwnd"]) != int(expected):
            return "拒绝切换：该窗口不是当前任务绑定的目标窗口。"

        if not self._force_foreground(target["hwnd"]):
            current = self._get_window_title(user32.GetForegroundWindow())
            return f"窗口切换失败，当前前台仍是：{current or '未知窗口'}"

        self.runtime.record_desktop_action("focus_window")
        current = self._get_window_title(user32.GetForegroundWindow())
        return f"窗口已真实切换到前台。当前前台窗口：{current}"

    def bring_app_to_foreground(self, title_keyword: str) -> str:
        """把已运行的当前任务目标窗口拉到前台并验证。"""
        return self.focus_window(title_keyword)

    # ---------------- low-level input ----------------

    @staticmethod
    def _send_input(obj):
        return user32.SendInput(
            1,
            ctypes.byref(obj),
            ctypes.sizeof(INPUT),
        ) == 1

    def _send_unicode_char(self, char):
        units = char.encode("utf-16-le")
        for i in range(0, len(units), 2):
            unit = int.from_bytes(units[i:i+2], "little")

            down = INPUT(type=INPUT_KEYBOARD)
            down.union.ki = KEYBDINPUT(
                wVk=0, wScan=unit, dwFlags=KEYEVENTF_UNICODE,
                time=0, dwExtraInfo=None,
            )
            up = INPUT(type=INPUT_KEYBOARD)
            up.union.ki = KEYBDINPUT(
                wVk=0, wScan=unit,
                dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                time=0, dwExtraInfo=None,
            )
            if not self._send_input(down):
                return False
            if not self._send_input(up):
                return False
        return True

    def _send_vk(self, vk, key_up=False):
        obj = INPUT(type=INPUT_KEYBOARD)
        obj.union.ki = KEYBDINPUT(
            wVk=int(vk),
            wScan=0,
            dwFlags=KEYEVENTF_KEYUP if key_up else 0,
            time=0,
            dwExtraInfo=None,
        )
        return self._send_input(obj)

    def mouse_click(self, x: int, y: int, button: str = "left") -> str:
        """按真实屏幕像素坐标点击；需要 mouse 权限。"""
        if not self.permission.has("mouse"):
            return "当前任务没有 mouse 权限。"
        if not self.desktop_target_ok():
            self.runtime.clear_desktop_task()
            return "目标窗口已不在前台，任务授权已自动失效。"

        try:
            x, y = int(x), int(y)
        except Exception:
            return "鼠标坐标必须是整数。"

        # 虚拟桌面范围，兼容多显示器负坐标。
        left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        top = user32.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN
        width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN

        if not (left <= x < left + width and top <= y < top + height):
            return "拒绝点击：坐标超出虚拟桌面范围。"

        if not user32.SetCursorPos(x, y):
            return "鼠标移动失败。"

        time.sleep(0.05)
        if str(button).lower() == "right":
            down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        else:
            down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

        for flag in (down_flag, up_flag):
            obj = INPUT(type=INPUT_MOUSE)
            obj.union.mi = MOUSEINPUT(
                dx=0, dy=0, mouseData=0, dwFlags=flag,
                time=0, dwExtraInfo=None,
            )
            if not self._send_input(obj):
                return "鼠标点击失败。"

        self.runtime.record_desktop_action("mouse_click")
        return f"已在 ({x}, {y}) 执行{button}键点击。"

    def keyboard_type(self, text_to_type: str) -> str:
        """向当前任务目标窗口输入 Unicode 文本；需要 keyboard 权限。"""
        if not self.permission.has("keyboard"):
            return "当前任务没有 keyboard 权限。"
        if not self.desktop_target_ok():
            self.runtime.clear_desktop_task()
            return "目标窗口已不在前台，任务授权已自动失效。"

        content = str(text_to_type)
        if not content:
            return "没有提供要输入的文字。"
        if len(content) > 2000:
            return "拒绝输入：单次最多 2000 个字符。"

        for char in content:
            if not self._send_unicode_char(char):
                return "键盘输入过程中失败。"

        self.runtime.record_desktop_action("keyboard_type")
        return "已输入指定文字。"

    def press_key(self, key: str) -> str:
        """发送一个功能键，如 enter/tab/esc；需要 keyboard 权限。"""
        if not self.permission.has("keyboard"):
            return "当前任务没有 keyboard 权限。"
        if not self.desktop_target_ok():
            self.runtime.clear_desktop_task()
            return "目标窗口已不在前台，任务授权已自动失效。"

        normalized = str(key).strip().lower()
        vk = VK_CODES.get(normalized)
        if vk is None:
            return f"不支持按键：{key}"

        if not self._send_vk(vk):
            return "按键按下失败。"
        if not self._send_vk(vk, key_up=True):
            return "按键释放失败。"

        self.runtime.record_desktop_action(f"press_key:{normalized}")
        return f"已按下：{normalized}"

    def keyboard_shortcut(self, keys: list) -> str:
        """发送简单组合键，如 ['ctrl','l']；需要 keyboard 权限。"""
        if not self.permission.has("keyboard"):
            return "当前任务没有 keyboard 权限。"
        if not self.desktop_target_ok():
            self.runtime.clear_desktop_task()
            return "目标窗口已不在前台，任务授权已自动失效。"

        if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
            return "快捷键必须是包含 1 到 4 个按键的列表。"

        normalized = [str(k).strip().lower() for k in keys]
        try:
            codes = [VK_CODES[k] for k in normalized]
        except KeyError as e:
            return f"不支持快捷键中的按键：{e.args[0]}"

        for vk in codes:
            if not self._send_vk(vk):
                return "快捷键按下失败。"
        for vk in reversed(codes):
            if not self._send_vk(vk, key_up=True):
                return "快捷键释放失败。"

        joined = "+".join(normalized)
        self.runtime.record_desktop_action(f"keyboard_shortcut:{joined}")
        return f"已执行快捷键：{joined}"

    def browser_search_new_tab(self, query: str) -> str:
        """在当前授权浏览器中新建标签页、输入搜索词并提交。"""
        if not self.runtime.desktop_has("keyboard"):
            return "当前桌面任务没有键盘输入权限。"
        if not self.desktop_target_ok():
            self.runtime.clear_desktop_task()
            return "目标浏览器窗口已不在前台，任务授权已失效。"

        query = str(query).strip()
        if not query:
            return "没有提供搜索内容。"
        if len(query) > 500:
            return "搜索内容过长，最多 500 个字符。"

        # Ctrl+T
        if not self._send_vk(VK_CODES["ctrl"]):
            return "Ctrl 按下失败。"
        if not self._send_vk(VK_CODES["t"]):
            self._send_vk(VK_CODES["ctrl"], key_up=True)
            return "T 按下失败。"
        self._send_vk(VK_CODES["t"], key_up=True)
        self._send_vk(VK_CODES["ctrl"], key_up=True)

        time.sleep(0.25)

        for char in query:
            if not self._send_unicode_char(char):
                return "搜索词输入失败。"

        time.sleep(0.1)

        if not self._send_vk(VK_CODES["enter"]):
            return "Enter 按下失败。"
        if not self._send_vk(VK_CODES["enter"], key_up=True):
            return "Enter 释放失败。"

        self.runtime.record_desktop_action("browser_search_new_tab")
        return f"已在新的浏览器标签页中提交搜索：{query}"

    def scroll(self, amount: int) -> str:
        """滚动当前任务目标窗口；正数向上，负数向下。"""
        if not self.permission.has("scroll"):
            return "当前任务没有 scroll 权限。"
        if not self.desktop_target_ok():
            self.runtime.clear_desktop_task()
            return "目标窗口已不在前台，任务授权已失效。"

        try:
            amount = max(-10, min(10, int(amount)))
        except Exception:
            return "滚动量必须是整数。"

        obj = INPUT(type=INPUT_MOUSE)
        obj.union.mi = MOUSEINPUT(
            dx=0, dy=0,
            mouseData=amount * WHEEL_DELTA,
            dwFlags=MOUSEEVENTF_WHEEL,
            time=0, dwExtraInfo=None,
        )
        if not self._send_input(obj):
            return "滚动失败。"

        self.runtime.record_desktop_action("scroll")
        return f"已滚动 {amount} 格。"
