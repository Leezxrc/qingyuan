import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

from .config import WORKSPACE
from .desktop import user32


class WeChatCapture:
    """
    微信实时截图器。

    所有“当前任务运行时截图”先进入：
    C:\\MyAgent\\workspace\\screenshots\\

    是否值得长期保存，由任务成功后
    WeChatExperienceLibrary 再决定。
    """

    def __init__(self, runtime):
        self.runtime = runtime

    def _get_target_hwnd(self):
        if not self.runtime.desktop_task_is_active():
            return None

        with self.runtime.desktop_lock:
            return self.runtime.desktop_task.get(
                "target_hwnd"
            )

    def get_window_rect(self):
        hwnd = self._get_target_hwnd()

        if not hwnd:
            return None

        if not user32.IsWindow(
            int(hwnd)
        ):
            return None

        rect = wintypes.RECT()

        ok = user32.GetWindowRect(
            int(hwnd),
            ctypes.byref(rect),
        )

        if not ok:
            return None

        if (
            rect.right <= rect.left
            or rect.bottom <= rect.top
        ):
            return None

        return (
            int(rect.left),
            int(rect.top),
            int(rect.right),
            int(rect.bottom),
        )

    def _save_image(
        self,
        image,
        label,
    ):
        temp_dir = (
            WORKSPACE
            / "screenshots"
        )

        temp_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_label = (
            str(label)
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

        path = temp_dir / (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            f"_{safe_label}.png"
        )

        image.save(
            path,
            format="PNG",
        )

        return path

    def capture_region(
        self,
        region,
        label="wechat_region",
    ):
        rect = self.get_window_rect()

        if rect is None:
            raise RuntimeError(
                "没有可用的已授权微信目标窗口。"
            )

        win_left, win_top, win_right, win_bottom = rect

        width = (
            win_right
            - win_left
        )

        height = (
            win_bottom
            - win_top
        )

        l_ratio, t_ratio, r_ratio, b_ratio = region

        left = int(
            win_left
            + width * l_ratio
        )

        top = int(
            win_top
            + height * t_ratio
        )

        right = int(
            win_left
            + width * r_ratio
        )

        bottom = int(
            win_top
            + height * b_ratio
        )

        if (
            right <= left
            or bottom <= top
        ):
            raise RuntimeError(
                "微信截图区域无效。"
            )

        image = ImageGrab.grab(
            bbox=(
                left,
                top,
                right,
                bottom,
            ),
            all_screens=True,
        )

        path = self._save_image(
            image,
            label,
        )

        return {
            "path": str(path),
            "rect": (
                left,
                top,
                right,
                bottom,
            ),
            "width": image.size[0],
            "height": image.size[1],
        }

    def capture(
        self,
        label="wechat",
    ):
        rect = self.get_window_rect()

        if rect is None:
            raise RuntimeError(
                "没有可用的已授权微信目标窗口。"
            )

        left, top, right, bottom = rect

        image = ImageGrab.grab(
            bbox=(
                left,
                top,
                right,
                bottom,
            ),
            all_screens=True,
        )

        path = self._save_image(
            image,
            label,
        )

        return {
            "path": str(path),
            "rect": rect,
            "width": image.size[0],
            "height": image.size[1],
        }
