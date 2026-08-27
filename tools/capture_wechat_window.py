"""
单独测试微信窗口截图。

运行：
cd C:\\MyAgent
.\\.venv\\Scripts\\python.exe tools\\capture_wechat_window.py

功能：
- 找到标题里包含“微信”的可见窗口
- 截取整个微信窗口
- 保存到：
  C:\\MyAgent\\workspace\\wechat_debug\\manual_wechat_capture.png
"""

import ctypes
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab


user32 = ctypes.windll.user32

try:
    user32.SetProcessDPIAware()
except Exception:
    pass


def get_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)

    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(
        length + 1
    )

    user32.GetWindowTextW(
        hwnd,
        buffer,
        len(buffer),
    )

    return buffer.value.strip()


windows = []


@ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,
    wintypes.LPARAM,
)
def callback(hwnd, lparam):
    if not user32.IsWindowVisible(hwnd):
        return True

    title = get_title(hwnd)

    if "微信" in title:
        windows.append(
            (
                int(hwnd),
                title,
            )
        )

    return True


user32.EnumWindows(
    callback,
    0,
)

if not windows:
    raise SystemExit(
        "没有找到标题包含“微信”的可见窗口。请先打开微信。"
    )

hwnd, title = windows[0]

rect = wintypes.RECT()

if not user32.GetWindowRect(
    hwnd,
    ctypes.byref(rect),
):
    raise SystemExit(
        "GetWindowRect 失败。"
    )

bbox = (
    int(rect.left),
    int(rect.top),
    int(rect.right),
    int(rect.bottom),
)

print(
    "找到微信窗口：",
    title,
)

print(
    "窗口坐标：",
    bbox,
)

image = ImageGrab.grab(
    bbox=bbox,
    all_screens=True,
)

out_dir = Path(
    r"C:\MyAgent\workspace\wechat_debug"
)

out_dir.mkdir(
    parents=True,
    exist_ok=True,
)

out = (
    out_dir
    / "manual_wechat_capture.png"
)

image.save(
    out,
    format="PNG",
)

print(
    "截图尺寸：",
    image.size,
)

print(
    "已保存：",
    out,
)
