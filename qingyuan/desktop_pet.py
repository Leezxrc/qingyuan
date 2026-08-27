"""
清渊桌宠 v1 表现层。

原则：
- 不承载大模型、记忆、RAG 或电脑权限。
- 只读取本机 Control API 状态并展示。
- 点击只触发 /wake，让下一轮语音进入连续对话窗口。
- 用户可把透明 PNG 放到 C:\\MyAgent\\assets\\qingyuan_pet.png 替换默认占位角色。
"""

import json
import os
import socket
import time
import tkinter as tk
from pathlib import Path
from urllib.request import urlopen

from .config import CONTROL_HOST, CONTROL_PORT


CONTROL_URL = f"http://{CONTROL_HOST}:{CONTROL_PORT}"
SINGLE_INSTANCE_HOST = "127.0.0.1"
SINGLE_INSTANCE_PORT = 8769
POLL_MS = 350
REPLY_VISIBLE_SECONDS = 10.0
TRANSPARENT_KEY = "#010203"
WINDOW_WIDTH = 280
WINDOW_HEIGHT = 350

ASSET_PATH = Path(r"C:\MyAgent\assets\qingyuan_pet.png")


class QingyuanPet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("清渊")
        self.root.geometry(
            f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+80+180"
        )
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_KEY)

        if os.name == "nt":
            try:
                self.root.wm_attributes(
                    "-transparentcolor",
                    TRANSPARENT_KEY,
                )
            except Exception:
                pass

        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.state = "offline"
        self.last_reply = ""
        self.last_reply_seen = 0.0
        self.last_reply_age = None
        self._drag_origin = None
        self._window_origin = None
        self._drag_moved = False
        self._avatar_image = None
        self._asset_loaded = False
        self._offline_since = None

        self.menu = tk.Menu(
            self.root,
            tearoff=0,
        )
        self.menu.add_command(
            label="唤醒清渊",
            command=self.wake,
        )
        self.menu.add_command(
            label="开启麦克风",
            command=lambda: self.request("/mic/on"),
        )
        self.menu.add_command(
            label="暂停麦克风",
            command=lambda: self.request("/mic/off"),
        )
        self.menu.add_command(
            label="进入待机",
            command=lambda: self.request("/standby"),
        )
        self.menu.add_command(
            label="停止当前说话",
            command=lambda: self.request("/stop"),
        )
        self.menu.add_separator()
        self.menu.add_command(
            label="只关闭桌宠",
            command=self.root.destroy,
        )

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)

        self.draw()
        self.root.after(100, self.poll_status)

    # -----------------------------------------------------
    # HTTP
    # -----------------------------------------------------

    @staticmethod
    def request(path):
        try:
            with urlopen(
                CONTROL_URL + path,
                timeout=1.2,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )
        except Exception:
            return None

    def wake(self):
        result = self.request("/wake")
        if result:
            self.state = "listening"
            self.draw()

    # -----------------------------------------------------
    # Window interaction
    # -----------------------------------------------------

    def on_press(self, event):
        self._drag_origin = (event.x_root, event.y_root)
        self._window_origin = (
            self.root.winfo_x(),
            self.root.winfo_y(),
        )
        self._drag_moved = False

    def on_drag(self, event):
        if not self._drag_origin or not self._window_origin:
            return

        dx = event.x_root - self._drag_origin[0]
        dy = event.y_root - self._drag_origin[1]

        if abs(dx) + abs(dy) > 5:
            self._drag_moved = True

        x = self._window_origin[0] + dx
        y = self._window_origin[1] + dy
        self.root.geometry(f"+{x}+{y}")

    def on_release(self, _event):
        if not self._drag_moved:
            self.wake()
        self._drag_origin = None
        self._window_origin = None

    def on_right_click(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # -----------------------------------------------------
    # State
    # -----------------------------------------------------

    @staticmethod
    def resolve_state(status):
        if not status or not status.get("ok"):
            return "offline"
        if not status.get("mic_enabled", False):
            return "mic_off"
        if status.get("confirming", False):
            return "confirming"
        if status.get("speaking", False):
            return "speaking"
        if status.get("desktop_active", False):
            return "working"
        if status.get("busy", False):
            return "thinking"
        if status.get("conversation_active", False):
            return "listening"
        return "standby"

    def poll_status(self):
        status = self.request("/status")
        new_state = self.resolve_state(status)

        if status:
            reply = str(status.get("last_reply", "")).strip()
            reply_age = status.get("last_reply_age")

            if reply and reply != self.last_reply:
                self.last_reply = reply
                self.last_reply_seen = time.monotonic()

            self.last_reply_age = reply_age
            self._offline_since = None
        else:
            if self._offline_since is None:
                self._offline_since = time.monotonic()

        if new_state != self.state:
            self.state = new_state
            self.draw()
        else:
            # 气泡需要按时间自动消失。
            self.draw()

        # Agent 已关闭一段时间后桌宠自行退出，避免留下孤儿窗口。
        if (
            self._offline_since is not None
            and time.monotonic() - self._offline_since > 8.0
        ):
            self.root.destroy()
            return

        self.root.after(POLL_MS, self.poll_status)

    # -----------------------------------------------------
    # Drawing
    # -----------------------------------------------------

    def state_text(self):
        return {
            "offline": "未连接",
            "mic_off": "麦克风暂停",
            "confirming": "等待确认",
            "speaking": "正在说话",
            "working": "正在执行",
            "thinking": "正在思考",
            "listening": "正在听你说",
            "standby": "待机",
        }.get(self.state, "待机")

    def bubble_visible(self):
        if not self.last_reply:
            return False

        if self.last_reply_age is not None:
            try:
                return float(self.last_reply_age) <= REPLY_VISIBLE_SECONDS
            except Exception:
                pass

        return (
            time.monotonic() - self.last_reply_seen
            <= REPLY_VISIBLE_SECONDS
        )

    def draw_round_rect(
        self,
        x1,
        y1,
        x2,
        y2,
        radius,
        **kwargs,
    ):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return self.canvas.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            **kwargs,
        )

    def try_draw_asset(self):
        if not ASSET_PATH.is_file():
            return False

        try:
            from PIL import Image, ImageTk

            image = Image.open(ASSET_PATH).convert("RGBA")
            image.thumbnail((190, 210))
            self._avatar_image = ImageTk.PhotoImage(image)
            self.canvas.create_image(
                WINDOW_WIDTH // 2,
                235,
                image=self._avatar_image,
                anchor="center",
            )
            self._asset_loaded = True
            return True
        except Exception:
            return False

    def draw_default_avatar(self):
        # 轻量占位身体；后续可直接替换为 PNG / Live2D 前端。
        cx = WINDOW_WIDTH // 2
        cy = 235

        state_accent = {
            "offline": "#777985",
            "mic_off": "#8b8d98",
            "confirming": "#f0c674",
            "speaking": "#74b9ff",
            "working": "#7ed6a5",
            "thinking": "#b49de2",
            "listening": "#86d8c4",
            "standby": "#a998d8",
        }.get(self.state, "#a998d8")

        # shadow
        self.canvas.create_oval(
            cx - 65,
            cy + 73,
            cx + 65,
            cy + 92,
            fill="#30313a",
            outline="",
        )

        # body / robe
        self.canvas.create_oval(
            cx - 72,
            cy - 6,
            cx + 72,
            cy + 86,
            fill="#252735",
            outline=state_accent,
            width=3,
        )

        # head
        self.canvas.create_oval(
            cx - 58,
            cy - 82,
            cx + 58,
            cy + 26,
            fill="#ececf5",
            outline=state_accent,
            width=4,
        )

        # hair / top crescent
        self.canvas.create_arc(
            cx - 60,
            cy - 92,
            cx + 60,
            cy + 17,
            start=10,
            extent=160,
            style="arc",
            outline="#56506f",
            width=8,
        )

        eye_y = cy - 35

        if self.state == "speaking":
            self.canvas.create_arc(
                cx - 35, eye_y - 5,
                cx - 10, eye_y + 10,
                start=200, extent=140,
                style="arc",
                outline="#30313a", width=3,
            )
            self.canvas.create_arc(
                cx + 10, eye_y - 5,
                cx + 35, eye_y + 10,
                start=200, extent=140,
                style="arc",
                outline="#30313a", width=3,
            )
            self.canvas.create_oval(
                cx - 8,
                cy - 9,
                cx + 8,
                cy + 4,
                fill="#6d5d78",
                outline="",
            )
        elif self.state == "thinking":
            self.canvas.create_oval(
                cx - 32, eye_y - 3,
                cx - 22, eye_y + 7,
                fill="#30313a", outline="",
            )
            self.canvas.create_oval(
                cx + 20, eye_y - 7,
                cx + 30, eye_y + 3,
                fill="#30313a", outline="",
            )
            self.canvas.create_line(
                cx - 7, cy - 2,
                cx + 7, cy - 2,
                fill="#555766", width=2,
            )
        else:
            self.canvas.create_oval(
                cx - 32, eye_y - 4,
                cx - 20, eye_y + 8,
                fill="#30313a", outline="",
            )
            self.canvas.create_oval(
                cx + 20, eye_y - 4,
                cx + 32, eye_y + 8,
                fill="#30313a", outline="",
            )
            self.canvas.create_arc(
                cx - 14,
                cy - 10,
                cx + 14,
                cy + 6,
                start=200,
                extent=140,
                style="arc",
                outline="#555766",
                width=2,
            )

        # chest mark
        self.canvas.create_text(
            cx,
            cy + 48,
            text="渊",
            fill=state_accent,
            font=("Microsoft YaHei UI", 18, "bold"),
        )

    def draw(self):
        self.canvas.delete("all")

        # bubble
        if self.bubble_visible():
            text = self.last_reply
            if len(text) > 90:
                text = text[:90] + "…"

            self.draw_round_rect(
                18,
                8,
                WINDOW_WIDTH - 18,
                112,
                18,
                fill="#f7f7fb",
                outline="#b8b3ce",
                width=2,
            )
            self.canvas.create_polygon(
                120, 110,
                144, 110,
                132, 126,
                fill="#f7f7fb",
                outline="#b8b3ce",
            )
            self.canvas.create_text(
                WINDOW_WIDTH // 2,
                57,
                text=text,
                width=220,
                justify="left",
                fill="#252535",
                font=("Microsoft YaHei UI", 10),
            )

        if not self.try_draw_asset():
            self.draw_default_avatar()

        # state pill
        self.draw_round_rect(
            77,
            318,
            203,
            344,
            12,
            fill="#22232b",
            outline="#6e6b7d",
            width=1,
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            331,
            text=self.state_text(),
            fill="#eeeeF4",
            font=("Microsoft YaHei UI", 9),
        )

    def run(self):
        self.root.mainloop()


def acquire_single_instance():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )
    try:
        sock.bind(
            (
                SINGLE_INSTANCE_HOST,
                SINGLE_INSTANCE_PORT,
            )
        )
        sock.listen(1)
        return sock
    except OSError:
        try:
            sock.close()
        except Exception:
            pass
        return None


def run():
    instance_socket = acquire_single_instance()
    if instance_socket is None:
        return

    app = QingyuanPet()
    try:
        app.run()
    finally:
        try:
            instance_socket.close()
        except Exception:
            pass


if __name__ == "__main__":
    run()
