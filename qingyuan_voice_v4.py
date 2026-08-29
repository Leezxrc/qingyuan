# -*- coding: utf-8 -*-
"""
清渊 Voice Core 4 - Phase 1 并行性能原型

目标：
1. 保留现有 STT 服务：
   WebRTC VAD -> SenseVoiceSmall -> 拼音唤醒 -> CAM++
2. 绕过旧 qingyuan.voice.voice_worker / Backend / AgentCore，
   直接验证“实时语音循环 + Ollama 流式输出 + 句子级 TTS Queue”。
3. 不修改任何 memory / data / knowledge / permission 文件。
4. Phase 1 只做普通对话性能验证，不执行电脑操作。

验证通过后，再把 Agent Core / 权限 / 记忆接回 V4。
"""

import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ollama import chat


BASE_DIR = Path(r"C:\MyAgent")

MODEL = "qwen3:4b-instruct"
MODEL_NUM_CTX = 6144
MODEL_KEEP_ALIVE = "30m"

STT_URL = "http://127.0.0.1:8766/listen"
STT_HEALTH = "http://127.0.0.1:8766/health"
STT_SHUTDOWN = "http://127.0.0.1:8766/shutdown"

TTS_URL = "http://127.0.0.1:8765/speak"
TTS_HEALTH = "http://127.0.0.1:8765/health"
TTS_SHUTDOWN = "http://127.0.0.1:8765/shutdown"

STT_PYTHON = Path(
    r"C:\Users\leezx\miniconda3\envs\chatAudio\python.exe"
)
STT_SCRIPT = BASE_DIR / "qingyuan_stt_server.py"

TTS_PYTHON = BASE_DIR / "cosyvoice_env" / "Scripts" / "python.exe"
TTS_SCRIPT = BASE_DIR / "CosyVoice" / "qingyuan_tts_server.py"

VOICE_SPEED = 1.5
ACTIVE_WINDOW_SECONDS = 45.0
MAX_PENDING_CHARS = 48

# 第一段出来后短暂等待后续句子，把极快生成的短回答合并成一次 TTS。
# 这样只多等约 0.45 秒，却能避免每句话都重复 3~4 秒的 TTS 启动成本。
TTS_COALESCE_SECONDS = 0.45

SYSTEM_PROMPT = """你是清渊，一个运行在用户本地电脑上的私人智能体。
这是 Voice Core 4 的语音性能测试模式。
回答应自然、简洁、直接。普通问题优先一到三句话。
当前测试模式不执行任何电脑操作、权限操作、长期记忆写入或文件修改。
"""


def _configure_utf8_stdio():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True,
                )
        except Exception:
            pass


_configure_utf8_stdio()


def http_get(url, timeout=2.0):
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read()
    except Exception:
        return None


def is_healthy(url):
    return http_get(url, timeout=1.5) is not None


def wait_health(url, name, timeout=60.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if is_healthy(url):
            print(f"[V4] {name} 已就绪")
            return True
        time.sleep(0.5)

    print(f"[V4] {name} 启动超时")
    return False


def start_service_if_needed(health_url, python_exe, script, name):
    if is_healthy(health_url):
        print(f"[V4] {name} 已经在运行")
        return None, False

    if not Path(python_exe).is_file():
        raise FileNotFoundError(python_exe)

    if not Path(script).is_file():
        raise FileNotFoundError(script)

    print(f"[V4] 正在启动 {name}……")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )

    proc = subprocess.Popen(
        [str(python_exe), str(script)],
        cwd=str(Path(script).parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    if not wait_health(health_url, name):
        try:
            proc.terminate()
        except Exception:
            pass
        raise RuntimeError(f"{name} 启动失败")

    return proc, True


def listen_once(standby):
    params = {
        "standby": "1" if standby else "0",
        "barge": "0",
    }

    url = STT_URL + "?" + urlencode(params)

    try:
        with urlopen(url, timeout=3600) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )
    except Exception as exc:
        print(f"[V4][STT] 请求失败：{exc}")
        return ""

    return str(data.get("text", "")).strip()


def strip_wake_word(text):
    value = str(text).strip()

    if value.startswith("清渊"):
        value = value[2:].lstrip("，,。.!！?？ ")

    return value or "在吗"


tts_queue = queue.Queue()
tts_stop_event = threading.Event()

_first_tts_started = threading.Event()
_turn_started_at = 0.0


def post_tts(text):
    payload = json.dumps(
        {
            "text": text,
            "speed": VOICE_SPEED,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = Request(
        TTS_URL,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        },
        method="POST",
    )

    with urlopen(req, timeout=3600) as response:
        response.read()


def tts_worker():
    while not tts_stop_event.is_set():
        try:
            item = tts_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        if item is None:
            tts_queue.task_done()
            return

        batch = [item]
        stop_after_batch = False

        # 给模型一个很短的“追上窗口”。
        # 对你当前 4B 模型，三句话往往 1 秒内已经生成完；
        # 把它们并成一次 /speak，可以显著减少句间空白。
        deadline = time.monotonic() + TTS_COALESCE_SECONDS

        while True:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                break

            try:
                extra = tts_queue.get(timeout=remaining)
            except queue.Empty:
                break

            if extra is None:
                tts_queue.task_done()
                stop_after_batch = True
                break

            batch.append(extra)

        texts = [
            str(part[0]).strip()
            for part in batch
            if str(part[0]).strip()
        ]

        text = " ".join(texts)
        queued_at = min(part[1] for part in batch)

        try:
            now = time.monotonic()

            if not _first_tts_started.is_set():
                _first_tts_started.set()
                print(
                    f"\n[V4][计时] 第一批进入 TTS："
                    f"{now - _turn_started_at:.2f}s"
                )

            print(
                f"\n[V4][TTS] 合并 {len(batch)} 段后开始：{text}"
                f"  (首段排队 {now - queued_at:.2f}s)"
            )

            post_tts(text)

            print(f"[V4][TTS] 完成：{text}")

        except URLError as exc:
            print(f"[V4][TTS] 服务不可用：{exc}")
        except Exception as exc:
            print(f"[V4][TTS] 失败：{exc}")
        finally:
            for _ in batch:
                tts_queue.task_done()

        if stop_after_batch:
            return


SENTENCE_END_RE = re.compile(r"^(.+?[。！？!?；;\n])", re.S)


class SentenceStreamer:
    def __init__(self):
        self.pending = ""

    def feed(self, piece):
        self.pending += str(piece or "")
        ready = []

        while True:
            match = SENTENCE_END_RE.match(self.pending)

            if match:
                sentence = match.group(1).strip()
                self.pending = self.pending[
                    match.end():
                ]

                if sentence:
                    ready.append(sentence)
                continue

            if len(self.pending) >= MAX_PENDING_CHARS:
                cut = -1

                for mark in ("，", ",", "、", "：", ":"):
                    pos = self.pending.rfind(
                        mark,
                        0,
                        MAX_PENDING_CHARS + 1,
                    )
                    cut = max(cut, pos)

                if cut < 12:
                    cut = MAX_PENDING_CHARS - 1

                sentence = self.pending[:cut + 1].strip()
                self.pending = self.pending[cut + 1:]

                if sentence:
                    ready.append(sentence)
                continue

            break

        return ready

    def flush(self):
        value = self.pending.strip()
        self.pending = ""
        return value


messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }
]


def run_llm_turn(user_text):
    global _turn_started_at

    messages.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    if len(messages) > 12:
        del messages[1:-10]

    _first_tts_started.clear()
    _turn_started_at = time.monotonic()

    first_token_at = None
    first_sentence_at = None

    streamer = SentenceStreamer()
    full_text = ""

    print("\n清渊：", end="", flush=True)

    stream = chat(
        model=MODEL,
        messages=messages,
        think=False,
        stream=True,
        keep_alive=MODEL_KEEP_ALIVE,
        options={
            "num_ctx": MODEL_NUM_CTX,
        },
    )

    for chunk in stream:
        piece = getattr(
            chunk.message,
            "content",
            "",
        ) or ""

        if not piece:
            continue

        now = time.monotonic()

        if first_token_at is None:
            first_token_at = now
            print(
                f"\n[V4][计时] Ollama 首 token："
                f"{first_token_at - _turn_started_at:.2f}s"
            )
            print("清渊：", end="", flush=True)

        print(piece, end="", flush=True)
        full_text += piece

        for sentence in streamer.feed(piece):
            if first_sentence_at is None:
                first_sentence_at = time.monotonic()
                print(
                    f"\n[V4][计时] 第一段文字可播："
                    f"{first_sentence_at - _turn_started_at:.2f}s"
                )
                print("清渊：", end="", flush=True)

            tts_queue.put(
                (
                    sentence,
                    time.monotonic(),
                )
            )

    tail = streamer.flush()

    if tail:
        if first_sentence_at is None:
            first_sentence_at = time.monotonic()
            print(
                f"\n[V4][计时] 第一段文字可播："
                f"{first_sentence_at - _turn_started_at:.2f}s"
            )
            print("清渊：", end="", flush=True)

        tts_queue.put(
            (
                tail,
                time.monotonic(),
            )
        )

    print()

    messages.append(
        {
            "role": "assistant",
            "content": full_text,
        }
    )

    llm_done = time.monotonic()

    print(
        f"[V4][计时] LLM 完整生成："
        f"{llm_done - _turn_started_at:.2f}s"
    )

    tts_queue.join()

    all_done = time.monotonic()

    print(
        f"[V4][计时] 本轮语音全部完成："
        f"{all_done - _turn_started_at:.2f}s"
    )


def main():
    print("=" * 64)
    print("清渊 Voice Core 4 - Phase 1.1")
    print("实时监听 + Ollama 流式输出 + 自适应 TTS 合并队列")
    print("注意：当前仅为性能原型，不执行电脑操作，不写长期记忆。")
    print("=" * 64)

    started_services = []

    try:
        tts_proc, tts_started = start_service_if_needed(
            TTS_HEALTH,
            TTS_PYTHON,
            TTS_SCRIPT,
            "CosyVoice TTS",
        )

        if tts_started:
            started_services.append(
                (tts_proc, TTS_SHUTDOWN)
            )

        stt_proc, stt_started = start_service_if_needed(
            STT_HEALTH,
            STT_PYTHON,
            STT_SCRIPT,
            "SenseVoice STT",
        )

        if stt_started:
            started_services.append(
                (stt_proc, STT_SHUTDOWN)
            )

        worker = threading.Thread(
            target=tts_worker,
            daemon=True,
            name="qingyuan-v4-tts",
        )
        worker.start()

        active_until = 0.0

        print()
        print("[V4] 已就绪。待机状态请说：清渊 + 你的问题")

        while True:
            active = time.monotonic() < active_until

            text = listen_once(
                standby=not active
            )

            if not text:
                time.sleep(0.1)
                continue

            print(f"\n你：{text}")

            command = (
                text
                if active
                else strip_wake_word(text)
            )

            if command.lower().strip() in {
                "退出",
                "退出清渊",
                "关闭清渊",
                "exit",
                "quit",
            }:
                print("\n清渊：Voice Core 4 测试结束。")
                break

            run_llm_turn(command)

            active_until = (
                time.monotonic()
                + ACTIVE_WINDOW_SECONDS
            )

    except KeyboardInterrupt:
        print("\n[V4] 手动停止。")

    finally:
        tts_stop_event.set()

        try:
            tts_queue.put_nowait(None)
        except Exception:
            pass

        for proc, shutdown_url in reversed(
            started_services
        ):
            http_get(
                shutdown_url,
                timeout=1.0,
            )

            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
