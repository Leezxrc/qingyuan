import queue
import threading
import time

from .config import (
    ACTIVE_WINDOW_SECONDS,
    DESKTOP_TASK_IDLE_TIMEOUT_SECONDS,
)


class RuntimeState:
    def __init__(self):
        self.input_queue = queue.Queue()
        self.confirm_queue = queue.Queue()

        self.stop_event = threading.Event()

        # 当前任务紧急取消。
        # stop_event = 退出整个清渊
        # cancel_event = 只中止当前任务
        self.cancel_event = threading.Event()
        self.agent_busy = threading.Event()
        self.confirm_active = threading.Event()
        self.tts_speaking = threading.Event()

        # TTS 自回声过滤状态
        self.echo_lock = threading.Lock()
        self.last_tts_text = ""
        self.last_tts_end_time = 0.0

        # 桌宠表现层读取的最近回复。
        # 仅驻留内存，不写入 memory / data / knowledge。
        self.assistant_reply_lock = threading.Lock()
        self.last_assistant_text = ""
        self.last_assistant_time = 0.0

        self.voice_enabled = True
        self.voice_listen_enabled = True

        self.conversation_lock = threading.Lock()
        self.conversation_active_until = 0.0

        # 控制台状态提示：
        # - 每次有效活动后，“正在听”只显示一次
        # - 45 秒无活动后，“休息啦”只显示一次
        self.listen_status_lock = threading.Lock()
        self.listening_notice_shown = False
        self.sleep_notice_shown = True
        self.had_conversation_activity = False

        self.desktop_lock = threading.Lock()
        self.desktop_task = {
            "active": False,
            "description": "",
            "target_hwnd": None,
            "target_title": "",
            "capabilities": set(),
            "last_activity": 0.0,
            "action_count": 0,
            "action_types": set(),
            "targets": [],
            "original_request": "",
        }

    # ---------------- conversation ----------------

    def mark_activity(self, source="activity"):
        with self.conversation_lock:
            self.conversation_active_until = (
                time.monotonic() + ACTIVE_WINDOW_SECONDS
            )

        with self.listen_status_lock:
            self.had_conversation_activity = True
            self.sleep_notice_shown = False
            # 新活动发生后，允许下一轮等待时重新显示一次“正在听”。
            self.listening_notice_shown = False

    def activate_conversation(self):
        self.mark_activity("conversation")

    def go_standby(self):
        with self.conversation_lock:
            self.conversation_active_until = 0.0

        with self.listen_status_lock:
            self.listening_notice_shown = False
            self.sleep_notice_shown = True

    def is_conversation_active(self):
        with self.conversation_lock:
            return time.monotonic() < self.conversation_active_until

    def active_remaining(self):
        with self.conversation_lock:
            return max(
                0.0,
                self.conversation_active_until - time.monotonic(),
            )

    # ---------------- console listening status ----------------

    def show_listening_once(self):
        """
        当前等待周期只显示一次“清渊正在听”。
        """
        with self.listen_status_lock:
            if self.listening_notice_shown:
                return False

            self.listening_notice_shown = True

        print("\n🎤 清渊正在听……")
        return True

    def mark_input_received(self):
        """
        收到真实用户输入后结束本轮“正在听”状态。
        下一次进入等待时允许重新显示。
        """
        with self.listen_status_lock:
            self.listening_notice_shown = False

    def should_show_sleep_notice(self):
        """
        只在真正空闲时显示“清渊休息啦”。

        以下任一状态存在时都不能进入休息提示：
        - Agent 正在处理用户命令
        - 正在等待用户确认
        - 有有效桌面任务许可证
        - 45 秒连续会话仍有效
        """
        if self.agent_busy.is_set():
            return False

        if self.confirm_active.is_set():
            return False

        if self.desktop_task_is_active():
            return False

        if self.is_conversation_active():
            return False

        with self.listen_status_lock:
            if not self.had_conversation_activity:
                return False

            if self.sleep_notice_shown:
                return False

            self.sleep_notice_shown = True
            self.listening_notice_shown = False
            return True

    # ---------------- desktop pet / presentation ----------------

    def set_last_assistant_text(self, text):
        value = str(text).strip()
        if not value:
            return

        with self.assistant_reply_lock:
            self.last_assistant_text = value
            self.last_assistant_time = time.monotonic()

    def get_last_assistant_text(self):
        with self.assistant_reply_lock:
            return (
                self.last_assistant_text,
                self.last_assistant_time,
            )

    # ---------------- desktop task ----------------

    def clear_desktop_task(self, preserve_request=False):
        with self.desktop_lock:
            original_request = (
                self.desktop_task.get(
                    "original_request",
                    "",
                )
                if preserve_request
                else ""
            )

            self.desktop_task.update({
                "active": False,
                "description": "",
                "target_hwnd": None,
                "target_title": "",
                "capabilities": set(),
                "last_activity": 0.0,
                "action_count": 0,
                "action_types": set(),
                "targets": [],
                "original_request": original_request,
            })

    def desktop_task_is_active(self):
        with self.desktop_lock:
            if not self.desktop_task["active"]:
                return False

            if (
                time.monotonic() - self.desktop_task["last_activity"]
                > DESKTOP_TASK_IDLE_TIMEOUT_SECONDS
            ):
                self.desktop_task.update({
                    "active": False,
                    "description": "",
                    "target_hwnd": None,
                    "target_title": "",
                    "capabilities": set(),
                    "last_activity": 0.0,
                    "action_count": 0,
                    "action_types": set(),
                    "targets": [],
                })
                return False

            return True

    def desktop_has(self, capability):
        if not self.desktop_task_is_active():
            return False
        with self.desktop_lock:
            return capability in self.desktop_task["capabilities"]

    def refresh_desktop_task(self):
        if self.desktop_task_is_active():
            with self.desktop_lock:
                self.desktop_task["last_activity"] = time.monotonic()
            self.mark_activity("desktop")

    def record_desktop_action(self, action_name):
        if not self.desktop_task_is_active():
            return
        with self.desktop_lock:
            self.desktop_task["action_count"] += 1
            self.desktop_task["action_types"].add(action_name)
            self.desktop_task["last_activity"] = time.monotonic()
        self.mark_activity(action_name)

    def desktop_action_count(self):
        if not self.desktop_task_is_active():
            return 0
        with self.desktop_lock:
            return int(self.desktop_task["action_count"])

    def desktop_action_types(self):
        if not self.desktop_task_is_active():
            return set()
        with self.desktop_lock:
            return set(self.desktop_task["action_types"])


# ============================================================
# Emergency task cancel compatibility helpers
# ============================================================

def _request_task_cancel(self):
    self.cancel_event.set()


def _clear_task_cancel(self):
    self.cancel_event.clear()


def _task_cancelled(self):
    return self.cancel_event.is_set()


if not hasattr(RuntimeState, "request_task_cancel"):
    RuntimeState.request_task_cancel = _request_task_cancel

if not hasattr(RuntimeState, "clear_task_cancel"):
    RuntimeState.clear_task_cancel = _clear_task_cancel

if not hasattr(RuntimeState, "task_cancelled"):
    RuntimeState.task_cancelled = _task_cancelled
