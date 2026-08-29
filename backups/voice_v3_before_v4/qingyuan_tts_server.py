import sys
import json
import re
import queue
import threading
import time


# ============================================================
# Windows / Launcher 日志 UTF-8
# ============================================================
#
# 清渊通过 Launcher 后台启动 TTS 时，stdout/stderr 会被重定向到日志。
# Windows 中文环境下 Python 可能默认使用 GBK；日志中的 🔊 / ▶ / ⏹ 等
# Unicode 字符会触发 UnicodeEncodeError，并直接杀死 playback_worker。
#
# 必须在模型加载、工作线程启动之前统一切换为 UTF-8。
def _configure_utf8_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)

        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True,
                    write_through=True,
                )
        except Exception:
            # 日志编码修复本身不能阻止 TTS 服务启动。
            pass


_configure_utf8_stdio()


import numpy as np
import sounddevice as sd

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


sys.path.append(
    r"C:\MyAgent\CosyVoice\third_party\Matcha-TTS"
)

from cosyvoice.cli.cosyvoice import AutoModel


# ============================================================
# 配置
# ============================================================

HOST = "127.0.0.1"
PORT = 8765

# 你之前确认 1.5 秒比较自然
START_BUFFER_SECONDS = 2.0

# 播放时切成小块，保证 /stop 可以快速打断
PLAYBACK_FRAME_SECONDS = 0.05

# Windows 默认声音映射器。直接打开 Sonos 端点在本机可正常返回但无声，
# 交给 Windows 默认输出路由后可正常播放到 Sonos。
OUTPUT_DEVICE = 5
OUTPUT_SAMPLE_RATE = 48000

MODEL_DIR = (
    r"C:\MyAgent\CosyVoice\pretrained_models"
    r"\Fun-CosyVoice3-0.5B"
)

REFERENCE_WAV = (
    r"C:\MyAgent\voice\qingyuan_reference.wav"
)

# 清渊音色缓存 ID：服务启动时只提取一次参考音特征，
# 后续每次回复直接复用，避免重复处理 reference wav / prompt。
ZERO_SHOT_SPK_ID = "qingyuan_voice"


# ============================================================
# 清渊母声对应原文
# ============================================================

PROMPT_TEXT = """
有些问题并没有想象中那么复杂。先整理已知条件，再决定下一步。保持冷静，答案往往比预想中更清晰。

I prefer clarity over haste. A good answer should be precise, calm, and useful. Take your time. We can work through it together.
""".strip()


COSYVOICE_PROMPT = (
    "You are a helpful assistant."
    "<|endofprompt|>"
    + PROMPT_TEXT
)


# ============================================================
# 全局状态
# ============================================================

STOP_SIGNAL = object()

stop_speech_event = threading.Event()
speak_lock = threading.Lock()


# ============================================================
# 加载模型
# ============================================================

print("=" * 60)
print("正在加载清渊语音系统……")
print("=" * 60)

cosyvoice = AutoModel(
    model_dir=MODEL_DIR
)

print("清渊语音模型加载成功")
print("采样率：", cosyvoice.sample_rate)

print("正在缓存清渊音色……")
cache_start = time.time()

try:
    cosyvoice.add_zero_shot_spk(
        COSYVOICE_PROMPT,
        REFERENCE_WAV,
        ZERO_SHOT_SPK_ID,
    )
    print(
        "清渊音色缓存完成，耗时：",
        round(time.time() - cache_start, 2),
        "秒",
    )
except Exception as exc:
    print("清渊音色缓存失败：", repr(exc))
    raise

print("=" * 60)


# ============================================================
# 清理不适合朗读的 Markdown
# ============================================================

def prepare_for_speech(text: str) -> str:

    text = re.sub(
        r"```.*?```",
        "代码内容已经显示在屏幕上。",
        text,
        flags=re.S,
    )

    text = re.sub(
        r"https?://\S+",
        "链接已经显示在屏幕上。",
        text,
    )

    text = re.sub(
        r"[*_#>`~]",
        "",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# ============================================================
# 中英文拆分
# ============================================================

def _english_ratio(text: str) -> float:

    letters = sum(
        1
        for char in text
        if char.isascii()
        and char.isalpha()
    )

    visible = sum(
        1
        for char in text
        if not char.isspace()
    )

    if visible == 0:
        return 0.0

    return (
        letters
        / visible
    )


def _split_sentences(text: str):

    # 优先按完整句子切。
    # 这样一句中文里夹少量英文术语时，不会被拆成很多小段。
    parts = re.split(
        r'(?<=[。！？!?；;])\s*|\n+',
        text,
    )

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


def split_bilingual_text(text: str):

    sentences = _split_sentences(
        text
    )

    if not sentences:
        return []


    segments = []

    current = ""
    current_mode = None


    for sentence in sentences:

        ratio = _english_ratio(
            sentence
        )

        # 只有“明显以英文为主”的整句才单独视为英文段。
        # Chrome、Qwen、RTX 3080 等短英文术语夹在中文句子里，
        # 仍然作为一个完整中文语境句子交给 CosyVoice。
        mode = (
            "en"
            if ratio >= 0.55
            else "mixed"
        )


        if current_mode is None:

            current = sentence
            current_mode = mode

            continue


        # 同类句子合并，减少模型调用次数和停顿。
        if mode == current_mode:

            current += " " + sentence

            continue


        if current.strip():

            segments.append(
                current.strip()
            )


        current = sentence
        current_mode = mode


    if current.strip():

        segments.append(
            current.strip()
        )


    return segments


# ============================================================
# 可打断流式合成 + 播放
# ============================================================

def _resample_audio(audio, src_rate, dst_rate):
    """轻量线性重采样：CosyVoice 24 kHz -> Windows 输出 48 kHz。"""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)

    if src_rate == dst_rate or len(audio) <= 1:
        return audio

    dst_len = max(
        1,
        int(round(len(audio) * float(dst_rate) / float(src_rate)))
    )

    src_x = np.linspace(
        0.0,
        1.0,
        num=len(audio),
        endpoint=False,
        dtype=np.float64,
    )
    dst_x = np.linspace(
        0.0,
        1.0,
        num=dst_len,
        endpoint=False,
        dtype=np.float64,
    )

    return np.interp(
        dst_x,
        src_x,
        audio,
    ).astype(np.float32)


def speak(
    text: str,
    speed: float = 1.0
):

    with speak_lock:

        stop_speech_event.clear()

        text = prepare_for_speech(
            text
        )

        if not text:
            return False

        print("\n收到清渊回复：")
        print(text)

        segments = split_bilingual_text(
            text
        )

        audio_queue = queue.Queue()

        playback_started = False
        playback_thread = None

        buffered_seconds = 0.0

        start_time = time.time()
        first_audio_time = None

        interrupted = False

        frame_samples = max(
            1,
            int(
                OUTPUT_SAMPLE_RATE
                * PLAYBACK_FRAME_SECONDS
            )
        )


        def playback_worker():

            print(
                "\n🔊 清渊开始说话……"
            )

            with sd.OutputStream(
                samplerate=OUTPUT_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                latency="low",
                device=OUTPUT_DEVICE,
            ) as audio_stream:

                while True:

                    audio = audio_queue.get()

                    try:

                        if audio is STOP_SIGNAL:
                            break

                        # 已收到打断命令时，后续缓存直接丢弃。
                        if stop_speech_event.is_set():
                            continue

                        # 大音频块拆成约 50 ms 小块，
                        # 每一小块之间都检查是否被打断。
                        start = 0

                        while start < len(audio):

                            if stop_speech_event.is_set():
                                break

                            end = min(
                                start + frame_samples,
                                len(audio)
                            )

                            audio_stream.write(
                                audio[
                                    start:end
                                ].reshape(-1, 1)
                            )

                            start = end

                    finally:

                        audio_queue.task_done()

            if stop_speech_event.is_set():
                print(
                    "\n⏹ 清渊已被打断。"
                )
            else:
                print(
                    "\n🔊 播放完成。"
                )


        for segment_index, segment in enumerate(
            segments,
            start=1
        ):

            if stop_speech_event.is_set():
                interrupted = True
                break

            print(
                f"\n正在生成 {segment_index}/"
                f"{len(segments)}：{segment}"
            )

            for result in cosyvoice.inference_zero_shot(
                segment,
                "",
                "",
                zero_shot_spk_id=ZERO_SHOT_SPK_ID,
                stream=True,
                speed=speed,
            ):

                if stop_speech_event.is_set():
                    interrupted = True
                    break

                audio = (
                    result["tts_speech"]
                    .detach()
                    .cpu()
                    .squeeze(0)
                    .numpy()
                    .astype(np.float32)
                )

                duration = (
                    len(audio)
                    / cosyvoice.sample_rate
                )

                if first_audio_time is None:

                    first_audio_time = (
                        time.time()
                        - start_time
                    )

                    print(
                        "\n第一块音频耗时：",
                        round(
                            first_audio_time,
                            2
                        ),
                        "秒"
                    )

                playback_audio = _resample_audio(
                    audio,
                    cosyvoice.sample_rate,
                    OUTPUT_SAMPLE_RATE,
                )

                audio_queue.put(
                    playback_audio
                )

                buffered_seconds += (
                    duration
                )

                if (
                    not playback_started
                    and buffered_seconds
                    >= START_BUFFER_SECONDS
                ):

                    playback_started = True

                    print(
                        "\n▶ 已达到启动缓冲：",
                        round(
                            buffered_seconds,
                            2
                        ),
                        "秒"
                    )

                    playback_thread = (
                        threading.Thread(
                            target=playback_worker,
                            daemon=True,
                        )
                    )

                    playback_thread.start()

            if interrupted:
                break


        # 很短的句子仍然需要启动播放线程，
        # 即使此时已经被打断，也让线程负责清空队列。
        if not playback_started:

            playback_started = True

            playback_thread = (
                threading.Thread(
                    target=playback_worker,
                    daemon=True,
                )
            )

            playback_thread.start()


        if stop_speech_event.is_set():
            interrupted = True


        audio_queue.put(
            STOP_SIGNAL
        )

        audio_queue.join()

        if playback_thread is not None:
            playback_thread.join()


        print(
            "\n本次语音总耗时：",
            round(
                time.time()
                - start_time,
                2
            ),
            "秒"
        )

        return interrupted


# ============================================================
# HTTP
# ============================================================

class QingyuanTTSHandler(
    BaseHTTPRequestHandler
):

    def send_json(
        self,
        status_code,
        data,
    ):

        payload = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(
            status_code
        )

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(payload)),
        )

        self.end_headers()

        self.wfile.write(
            payload
        )


    def do_GET(self):

        if self.path == "/health":

            self.send_json(
                200,
                {
                    "ok": True,
                    "name": "清渊 TTS",
                },
            )

            return


        if self.path == "/stop":

            stop_speech_event.set()

            self.send_json(
                200,
                {
                    "ok": True,
                    "stopped": True,
                },
            )

            return


        if self.path == "/shutdown":

            stop_speech_event.set()

            self.send_json(
                200,
                {
                    "ok": True,
                    "shutting_down": True,
                },
            )

            threading.Thread(
                target=self.server.shutdown,
                daemon=True,
            ).start()

            return


        self.send_json(
            404,
            {
                "ok": False,
                "error": "Not found",
            },
        )


    def do_POST(self):

        if self.path != "/speak":

            self.send_json(
                404,
                {
                    "ok": False,
                    "error": "Not found",
                },
            )

            return

        try:

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            body = self.rfile.read(
                content_length
            )

            data = json.loads(
                body.decode("utf-8")
            )

            text = str(
                data.get(
                    "text",
                    ""
                )
            ).strip()

            speed = float(
                data.get(
                    "speed",
                    1.0
                )
            )

            if not text:

                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": "text 不能为空",
                    },
                )

                return

            interrupted = speak(
                text=text,
                speed=speed,
            )

            self.send_json(
                200,
                {
                    "ok": True,
                    "interrupted": bool(
                        interrupted
                    ),
                },
            )

        except Exception as e:

            print(
                "\n语音生成失败：",
                e
            )

            self.send_json(
                500,
                {
                    "ok": False,
                    "error": str(e),
                },
            )


    def log_message(
        self,
        format,
        *args
    ):
        return


# ============================================================
# 启动
# ============================================================

server = ThreadingHTTPServer(
    (HOST, PORT),
    QingyuanTTSHandler,
)

print()
print("=" * 60)
print("清渊语音服务已启动")
print(f"http://{HOST}:{PORT}")
print("说话接口：/speak")
print("强制打断接口：/stop")
print("关闭接口：/shutdown")
print("保持这个窗口开启")
print("=" * 60)

try:

    server.serve_forever()

except KeyboardInterrupt:

    stop_speech_event.set()

    print(
        "\n清渊语音服务已关闭。"
    )

finally:

    server.server_close()
