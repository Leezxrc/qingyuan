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


STT_BARGE_URL = "http://127.0.0.1:8766/barge"


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

        conversation_was_active = False
        try:
            conversation_was_active = self.runtime.is_conversation_active()
        except Exception:
            conversation_was_active = False

        if conversation_was_active:
            self.runtime.mark_activity("tts_start")

        if allow_barge_in:
            self.runtime.tts_speaking.set()
            self._set_barge_mode(True)

        try:
            with urlopen(req, timeout=300) as response:
                response.read()
        except URLError:
            print("\n[语音] 清渊语音服务没有启动。")
        except Exception as e:
            print(f"\n[语音] 播放失败：{e}")
        finally:
            self._set_barge_mode(False)
            self.runtime.tts_speaking.clear()
            with self.runtime.echo_lock:
                self.runtime.last_tts_end_time = time.monotonic()
            # 长回答不应吃掉连续对话窗口。只在原本已处于连续对话时刷新，
            # 避免启动播报之类把待机状态错误激活。
            if conversation_was_active:
                try:
                    self.runtime.mark_activity("tts_end")
                except Exception:
                    pass

    def stop_speaking(self):
        self._get(TTS_STOP_URL, timeout=1.0)
        self._set_barge_mode(False)
        self.runtime.tts_speaking.clear()

    def _set_barge_mode(self, enabled: bool):
        value = "1" if enabled else "0"
        self._get(
            f"{STT_BARGE_URL}?enabled={value}",
            timeout=0.35,
        )
        with self.runtime.echo_lock:
            self.runtime.last_tts_end_time = time.monotonic()


    # ---------------- spoken response shaping ----------------

    @staticmethod
    def _spoken_clean(text):
        text = str(text or "")
        # 代码块不适合逐字朗读；屏幕仍保留完整正文。
        text = re.sub(r"```.*?```", " 详细代码请看屏幕。 " , text, flags=re.S)
        # Markdown / 列表符号转成自然停顿。
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
        text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
        text = text.replace("`", "")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _spoken_path_simplify(text):
        def repl(match):
            raw = match.group(0).replace("\\", "/")
            name = raw.rsplit("/", 1)[-1]
            if "." in name:
                name = name.rsplit(".", 1)[0]
            return name or "这个文件"

        # Windows 路径与项目相对路径只朗读末级文件名，完整路径仍在屏幕。
        text = re.sub(
            r"(?:[A-Za-z]:[\\/])?(?:[\w. -]+[\\/])+[\w.-]+",
            repl,
            text,
        )
        return text

    @staticmethod
    def _sentence_candidates(text):
        text = str(text or "").strip()
        if not text:
            return []
        parts = re.split(r"(?<=[。！？!?])\s*|\n+", text)
        result = []
        for part in parts:
            part = part.strip(" -•\t")
            if len(part) < 4:
                continue
            result.append(part)
        return result

    @staticmethod
    def _is_technical_response(text, intent=None):
        if str(intent or "").lower() == "coding":
            return True
        raw = str(text or "")
        if len(raw) < 220:
            return False
        markers = (
            "```", "traceback", "git diff", "pytest",
            ".py", ".js", ".ts", ".json", "C:\\",
            "[OK]", "exception", "error:",
        )
        marker_hits = sum(1 for marker in markers if marker.lower() in raw.lower())
        list_hits = len(re.findall(r"(?m)^\s*[-*+]\s+", raw))
        return marker_hits >= 1 or list_hits >= 3

    def _coding_summary_candidates(self, text):
        """优先朗读每个说明段落的第一句，跳过项目符号和代码细节。"""
        raw = re.sub(r"```.*?```", "", str(text or ""), flags=re.S)
        paragraphs = re.split(r"\n\s*\n+", raw)
        result = []
        for paragraph in paragraphs:
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            prose = [
                line for line in lines
                if not re.match(r"^[-*+•]\s*", line)
            ]
            if not prose:
                continue
            joined = " ".join(prose)
            first = re.split(r"(?<=[。！？!?])\s*", joined, maxsplit=1)[0].strip()
            if len(first) >= 4:
                result.append(first)
            if len(result) >= 3:
                break
        return result

    def prepare_spoken_text(self, text, intent=None, tool_results=None):
        """
        屏幕保留完整回答；这里只生成更适合 TTS 的口语版本。

        原则：
        - 普通短聊天保持原文，不额外总结；
        - Coding / 技术长回答只朗读核心结论；
        - 文件路径、代码块、diff、日志不逐字念；
        - 是否真的修改过文件以本轮真实 tool_results 为准。
        """
        original = str(text or "").strip()
        if not original:
            return ""

        if not self._is_technical_response(original, intent=intent):
            return original

        cleaned = self._spoken_clean(original)
        cleaned = self._spoken_path_simplify(cleaned)

        # 去掉适合屏幕、不适合口播的高密度技术标识。
        cleaned = re.sub(r"\b[a-zA-Z_][a-zA-Z0-9_]{18,}\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if str(intent or "").lower() == "coding":
            candidates = [
                self._spoken_path_simplify(self._spoken_clean(item))
                for item in self._coding_summary_candidates(original)
            ]
        else:
            candidates = self._sentence_candidates(cleaned)

        chosen = []
        total = 0
        for sentence in candidates:
            sentence = sentence.strip()
            if not sentence:
                continue
            # 内部工具/验证细节只显示在终端，不通过 TTS 朗读。
            lowered = sentence.lower()
            if any(token in lowered for token in (
                "code_finish_session",
                "coding_session_not_verified",
                "tool_call",
            )):
                continue
            if len(sentence) > 110:
                sentence = sentence[:107].rstrip("，,；; " ) + "。"
            if total + len(sentence) > 170 and chosen:
                break
            chosen.append(sentence)
            total += len(sentence)
            if len(chosen) >= 3:
                break

        if chosen:
            spoken = "我看完了。" + "".join(chosen)
        else:
            spoken = "我看完了，详细结果已经显示在屏幕上。"

        names = []
        for item in tool_results or []:
            try:
                names.append(str(item[0]))
            except Exception:
                pass

        if str(intent or "").lower() == "coding":
            wrote = "code_write_file" in names
            finished = any(
                name == "code_finish_session" and "CODING_SESSION_FINISHED" in str(result)
                for name, result in (tool_results or [])
                if isinstance(name, str)
            )
            if not wrote:
                spoken += "这次没有修改文件。"
            elif finished:
                spoken += "修改已经完成并通过了本轮验证。"
            else:
                spoken += "代码变更的详细状态请看屏幕。"

        # 口播上限，避免长篇技术回答拖慢首包并扩大自回声窗口。
        if len(spoken) > 220:
            spoken = spoken[:216].rstrip("，,；;。 " ) + "。详细内容请看屏幕。"

        return spoken

    def speak_response(self, text, intent=None, tool_results=None, allow_barge_in=True):
        spoken = self.prepare_spoken_text(
            text,
            intent=intent,
            tool_results=tool_results,
        )
        if not spoken:
            return
        if spoken.strip() != str(text or "").strip():
            print(f"\n[口播摘要] {spoken}")
        self.speak(spoken, allow_barge_in=allow_barge_in)

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

    @staticmethod
    def _ngram_coverage(short_text, long_text, n=2):
        """短句的字符 n-gram 有多少也出现在长句中。用于识别被 ASR 轻微听错的 TTS 片段。"""
        if len(short_text) < n or len(long_text) < n:
            return 0.0
        grams = [short_text[i:i+n] for i in range(len(short_text)-n+1)]
        if not grams:
            return 0.0
        hits = sum(1 for gram in grams if gram in long_text)
        return hits / len(grams)

    def _seconds_since_tts_end(self):
        with self.runtime.echo_lock:
            ended = self.runtime.last_tts_end_time
        if not ended:
            return None
        return time.monotonic() - ended

    def _looks_like_recent_tts_echo(self, text):
        """
        TTS 播放结束后的短时间内，如果 STT 结果与清渊刚说的话
        完整、局部或模糊高度重合，视为音箱 -> 麦克风自回声。

        重点解决：
        TTS: “任务没有完成：Coding Session 尚未调用 code_finish_session 完成验证。”
        STT: “尚未调用coded finish”
        这种被 ASR 截断并轻微听错后，旧版完整相似度过滤漏掉的问题。
        """
        with self.runtime.echo_lock:
            spoken = self.runtime.last_tts_text
            ended = self.runtime.last_tts_end_time

        if not spoken:
            return False

        # 打断期间 TTS 可能刚被 STT 服务停止，VoiceService 的 finally 还没来得及
        # 写入结束时间。因此“正在播报”也要启用回声比较。
        speaking_now = self.runtime.tts_speaking.is_set()
        if speaking_now:
            elapsed = 0.0
        elif ended:
            elapsed = time.monotonic() - ended
        else:
            return False

        # 只在短声学尾音窗口内使用强过滤，避免压制正常后续对话。
        if elapsed < 0 or elapsed > 4.5:
            return False

        a = self._echo_normalize(text)
        b = self._echo_normalize(spoken)

        if len(a) < 4 or len(b) < 4:
            return False

        if len(a) >= 6 and (a in b or b in a):
            return True

        ratio = SequenceMatcher(None, a, b).ratio()
        if ratio >= 0.72:
            return True

        short_text, long_text = (a, b) if len(a) <= len(b) else (b, a)
        match = SequenceMatcher(None, short_text, long_text).find_longest_match(
            0, len(short_text), 0, len(long_text)
        )
        longest_coverage = match.size / max(1, len(short_text))
        bigram_coverage = self._ngram_coverage(short_text, long_text, n=2)

        # ASR 对英文技术词可能多/少一个音节，因此采用局部覆盖而不是整句比值。
        return (
            len(short_text) >= 6
            and (
                bigram_coverage >= 0.72
                or longest_coverage >= 0.72
            )
        )

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

    def _looks_like_current_or_recent_tts_echo(self, text):
        with self.runtime.echo_lock:
            spoken = self.runtime.last_tts_text
            ended = self.runtime.last_tts_end_time

        if not spoken:
            return False

        a = self._echo_normalize(text)
        b = self._echo_normalize(spoken)

        if len(a) < 3 or len(b) < 3:
            return False

        if a in b or b in a:
            return True

        ratio = SequenceMatcher(None, a, b).ratio()

        if self.runtime.tts_speaking.is_set():
            return ratio >= 0.74

        elapsed = time.monotonic() - ended if ended else 999.0
        return 0 <= elapsed <= 2.5 and ratio >= 0.68

    def voice_worker(self):
        """
        Voice Core 3.0 frontend consumer.

        Important:
        - only ONE blocking STT /listen request exists;
        - STT owns the microphone continuously;
        - no separate "normal listen" and "barge-in listen" paths;
        - if a transcript arrives while TTS is speaking, the same utterance
          becomes the interrupting command and is routed exactly once.
        """
        while not self.runtime.stop_event.is_set():
            if not self.runtime.voice_listen_enabled:
                time.sleep(0.15)
                continue

            self.runtime.show_listening_once()

            # Voice Core 3 ignores standby/barge query flags. They remain here
            # only for backward API compatibility.
            text = self.listen(
                standby=not self.runtime.is_conversation_active(),
                barge=False,
            )

            if not text:
                time.sleep(0.08)
                continue

            # Confirmation owns the next voice transcript.
            if self.runtime.confirm_active.is_set():
                self.runtime.mark_input_received()

                if self._is_recent_duplicate_user_utterance(text):
                    print(f"\n[重复确认语音忽略] {text}")
                    continue

                print(f"\n你（确认语音）：{text}")
                self.runtime.confirm_queue.put(text)
                continue

            speaking = self.runtime.tts_speaking.is_set()

            # While Qingyuan is currently speaking, a different utterance
            # is a real barge-in. TTS echo is ignored before interrupting.
            if speaking:
                if self._looks_like_current_or_recent_tts_echo(text):
                    print(f"\n[播报回声忽略] {text}")
                    continue

                print(f"\n[语音打断] {text}")
                self.stop_speaking()

            # During LLM/tool generation there is no second listener.
            # A new utterance is queued once and will be processed in order.
            self._route_normal_voice(text)

