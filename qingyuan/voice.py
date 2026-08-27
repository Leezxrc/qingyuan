import json
import threading
import time
import re
from difflib import SequenceMatcher
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

from .config import (
    TTS_URL, TTS_STOP_URL, TTS_SHUTDOWN_URL,
    STT_URL, STT_CANCEL_URL, STT_SHUTDOWN_URL,
    VOICE_SPEED, CONFIRM_TIMEOUT_SECONDS,
)
from .wake import strip_wake_word


class VoiceService:
    def __init__(self, runtime):
        self.runtime = runtime
        self._last_user_utterance = ""
        self._last_user_utterance_time = 0.0

    # ---------------- TTS ----------------

    def speak(self, text, allow_barge_in=True):
        if not self.runtime.voice_enabled:
            return
        text = str(text).strip()
        if not text:
            return

        # 记录本次 TTS 文本，用于后续麦克风自回声过滤。
        with self.runtime.echo_lock:
            self.runtime.last_tts_text = text

        payload = json.dumps(
            {"text": text, "speed": VOICE_SPEED},
            ensure_ascii=False,
        ).encode("utf-8")

        req = Request(
            TTS_URL,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        if allow_barge_in:
            self.runtime.tts_speaking.set()

        try:
            with urlopen(req, timeout=300) as response:
                response.read()
        except URLError:
            print("\n[语音] 清渊语音服务没有启动。")
        except Exception as e:
            print(f"\n[语音] 播放失败：{e}")
        finally:
            self.runtime.tts_speaking.clear()
            with self.runtime.echo_lock:
                self.runtime.last_tts_end_time = time.monotonic()

    def stop_speaking(self):
        self._get(TTS_STOP_URL, timeout=1.0)
        self.runtime.tts_speaking.clear()

    # ---------------- STT ----------------

    def listen(self, standby=False, barge=False):
        params = {}
        if standby:
            params["standby"] = "1"
        if barge:
            params["barge"] = "1"

        url = STT_URL
        if params:
            url += "?" + urlencode(params)

        try:
            with urlopen(url, timeout=3600) as response:
                data = json.loads(response.read().decode("utf-8"))
            return str(data.get("text", "")).strip()
        except Exception:
            return ""

    def cancel_listen(self):
        self._get(STT_CANCEL_URL, timeout=1.0)

    def shutdown_voice_services(self):
        self.cancel_listen()
        self.stop_speaking()
        self._get(STT_SHUTDOWN_URL, timeout=1.5)
        self._get(TTS_SHUTDOWN_URL, timeout=1.5)

    def _get(self, url, timeout=1.0):
        try:
            with urlopen(url, timeout=timeout) as response:
                response.read()
        except Exception:
            pass

    # ---------------- confirmation ----------------

    @staticmethod
    def parse_confirmation(text):
        value = str(text).strip().lower().strip("。！!？，, ")

        # Whisper 对确认词的常见近音：
        # “同意”经常识别成“同一/统一”。
        confirmation_aliases = {
            "同一": "同意",
            "統一": "同意",
            "统一": "同意",
            "同億": "同意",
            "同义": "同意",
            "確認": "确认",
            "允許": "允许",
        }

        value = confirmation_aliases.get(
            value,
            value,
        )

        yes = {
            "y", "yes", "是", "同意", "可以", "确认", "允许",
            "继续", "好的", "好", "行", "可以的",
        }
        no = {
            "n", "no", "否", "不同意", "不可以", "不允许",
            "取消", "拒绝", "算了", "不要",
        }
        if value in yes:
            return True
        if value in no:
            return False
        return None

    def request_confirmation(
        self,
        prompt,
        operation_name="电脑操作",
        spoken_detail=None,
    ):
        print("\n" + "=" * 55)
        print("【清渊请求操作确认】")
        print(prompt)
        print()
        print("45 秒内：说“是 / 同意 / 可以 / 确认”，或键盘输入 y 继续。")
        print("说“否 / 不同意 / 不可以 / 取消”，或键盘输入 n 拒绝。")
        print("45 秒无回应将自动拒绝。")
        print("=" * 55)

        spoken = spoken_detail or f"清渊正在请求{operation_name}，请问是否同意？"
        self.speak(spoken, allow_barge_in=False)

        # 丢弃旧确认回答
        while True:
            try:
                self.runtime.confirm_queue.get_nowait()
            except Exception:
                break

        self.runtime.confirm_active.set()
        deadline = time.monotonic() + CONFIRM_TIMEOUT_SECONDS

        try:
            while time.monotonic() < deadline:
                try:
                    answer = self.runtime.confirm_queue.get(timeout=0.25)
                except Exception:
                    continue

                answer = str(answer).strip()
                if not answer:
                    continue

                parsed = self.parse_confirmation(answer)
                if parsed is True:
                    self.runtime.mark_activity("confirmation")
                    print(f"\n[确认] 已同意：{answer}")
                    return True
                if parsed is False:
                    self.runtime.mark_activity("confirmation")
                    print(f"\n[确认] 已拒绝：{answer}")
                    return False

                print(f"\n[确认] “{answer}”不是明确的同意或拒绝，继续等待。")

            print("\n[确认] 超时，按拒绝处理。")
            return False
        finally:
            self.runtime.confirm_active.clear()

    # ---------------- input workers ----------------

    def keyboard_worker(self):
        while not self.runtime.stop_event.is_set():
            try:
                text = input("\n你（键盘）：").strip()
            except (EOFError, KeyboardInterrupt):
                self.runtime.stop_event.set()
                return

            if not text:
                continue

            self.runtime.mark_activity("keyboard")

            if self.runtime.confirm_active.is_set():
                self.runtime.confirm_queue.put(text)
            else:
                self.runtime.input_queue.put(("keyboard", text))

    @staticmethod
    def _echo_normalize(text):
        text = str(text).lower()
        # 保留中英文数字，去掉标点/空白，降低 Whisper 标点差异影响。
        return re.sub(
            r"[^0-9a-z\u4e00-\u9fff]+",
            "",
            text,
        )

    def _looks_like_recent_tts_echo(self, text):
        """
        TTS 播放结束后的短时间内，如果 STT 结果和清渊刚说的话高度相似，
        视为音箱 -> 麦克风自回声，而不是用户新命令。
        """
        with self.runtime.echo_lock:
            spoken = self.runtime.last_tts_text
            ended = self.runtime.last_tts_end_time

        if not spoken or not ended:
            return False

        elapsed = time.monotonic() - ended

        # 房间/扬声器尾音一般在很短时间内被重新拾取。
        if elapsed < 0 or elapsed > 3.0:
            return False

        a = self._echo_normalize(text)
        b = self._echo_normalize(spoken)

        if len(a) < 4 or len(b) < 4:
            return False

        # 完整/局部重复
        if a in b or b in a:
            return True

        ratio = SequenceMatcher(
            None,
            a,
            b,
        ).ratio()

        return ratio >= 0.68

    @staticmethod
    def _dedupe_normalize(text):
        text = str(text).lower().strip()
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)

    def _is_recent_duplicate_user_utterance(self, text, window_seconds=2.0):
        normalized = self._dedupe_normalize(text)

        if not normalized:
            return False

        now = time.monotonic()
        previous = self._last_user_utterance
        elapsed = now - self._last_user_utterance_time

        self._last_user_utterance = normalized
        self._last_user_utterance_time = now

        return bool(
            previous
            and normalized == previous
            and 0 <= elapsed <= window_seconds
        )

    def _route_normal_voice(self, text):
        """
        把普通语音送入正常输入队列。
        也处理确认监听结束后“下一句话被误当成确认”的竞态。
        """
        text = str(text).strip()
        if not text:
            return

        self.runtime.mark_input_received()

        if self._is_recent_duplicate_user_utterance(text):
            print(f"\n[重复语音忽略] {text}")
            return

        if self._looks_like_recent_tts_echo(text):
            print(
                f"\n[自回声忽略] {text}"
            )
            return

        active = self.runtime.is_conversation_active()

        if active:
            self.runtime.mark_activity("voice")
            self.runtime.input_queue.put(("voice", text))
            return

        found, command = strip_wake_word(text)

        if not found:
            print(f"\n[待机忽略] {text}")
            return

        self.runtime.activate_conversation()

        if not command:
            command = "在吗"

        self.runtime.input_queue.put(("voice", command))

    def voice_worker(self):
        while not self.runtime.stop_event.is_set():
            if not self.runtime.voice_listen_enabled:
                time.sleep(0.2)
                continue

            # 确认阶段允许语音回答。
            if self.runtime.confirm_active.is_set():
                self.runtime.show_listening_once()
                text = self.listen(standby=False, barge=False)

                if not text:
                    time.sleep(0.25)
                    continue

                # STT 是阻塞请求，返回时确认可能已经结束。
                if self.runtime.confirm_active.is_set():
                    self.runtime.mark_input_received()

                    if self._is_recent_duplicate_user_utterance(text):
                        print(f"\n[重复确认语音忽略] {text}")
                        continue

                    print(f"\n你（确认语音）：{text}")
                    self.runtime.confirm_queue.put(text)
                    continue

                # 确认已结束：这句话是下一条正常命令。
                print(f"\n你（语音）：{text}")
                self._route_normal_voice(text)
                continue

            if self.runtime.agent_busy.is_set():
                time.sleep(0.1)
                continue

            active = self.runtime.is_conversation_active()

            self.runtime.show_listening_once()
            text = self.listen(
                standby=not active,
                barge=active and self.runtime.tts_speaking.is_set(),
            )

            if not text:
                # 二级保险：
                # STT 如果因服务重启/冲突立即返回空结果，
                # 不允许 voice loop 进入高速空轮询。
                time.sleep(0.25)
                continue

            self._route_normal_voice(text)
