import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import numpy as np
import pyaudio
import webrtcvad
from funasr import AutoModel
from modelscope.pipelines import pipeline
from pypinyin import Style, pinyin


# Launcher 会把 STT 输出重定向到日志文件。
# Windows 中文区域设置下 Python 可能把 stdout/stderr 识别成 GBK，
# 导致 🎤 / 🟢 等日志字符触发 UnicodeEncodeError。
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
except Exception:
    pass


# ============================================================
# 清渊 STT v2
# WebRTC VAD + SenseVoiceSmall + 拼音唤醒 + CAM++
# ============================================================

HOST = "127.0.0.1"
PORT = 8766

AUDIO_RATE = 16000
AUDIO_CHANNELS = 1
CHUNK = 1024
AUDIO_FORMAT = pyaudio.paInt16

# 不写死设备时使用 Windows / PyAudio 当前默认输入设备。
# 已实测当前默认设备为 Fifine Microphone。
MIC_DEVICE_ENV = os.environ.get("QINGYUAN_MIC_DEVICE", "").strip()

# 与已经实测通过的 ABexit 路线保持一致：
# 约 0.5 秒一组进行 VAD，静音约 1 秒结束一句话。
VAD_MODE = 3
VAD_WINDOW_SECONDS = 0.5
VAD_FRAME_MS = 10
VAD_SPEECH_RATIO = 0.50
NO_SPEECH_THRESHOLD = 1.0
MAX_RECORD_SECONDS = 30.0

# 第一次检测到语音时，额外带上前一个约 0.5 秒块，
# 防止句首“清渊”被截掉。
PRE_ROLL_BLOCKS = 1

# 打断 TTS 时额外保留一个非常轻量的音量门槛。
# 它只作用于 barge-in，不参与普通待机/对话 VAD。
BARGE_MIN_RMS = float(
    os.environ.get("QINGYUAN_BARGE_MIN_RMS", "0.025")
)

TTS_STOP_URL = "http://127.0.0.1:8765/stop"

SENSEVOICE_MODEL = os.environ.get(
    "QINGYUAN_SENSEVOICE_MODEL",
    "iic/SenseVoiceSmall",
).strip() or "iic/SenseVoiceSmall"

WAKE_PINYIN = ("qing", "yuan")

SPEAKER_VERIFY_ENABLED = (
    os.environ.get("QINGYUAN_SPEAKER_VERIFY", "1").strip()
    not in {"0", "false", "False", "no", "NO"}
)

SPEAKER_THRESHOLD = float(
    os.environ.get("QINGYUAN_SPEAKER_THRESHOLD", "0.35")
)

SPEAKER_MODEL = "damo/speech_campplus_sv_zh-cn_16k-common"
SPEAKER_MODEL_REVISION = "v1.0.0"

# 声纹属于用户持久化数据，不放进升级包默认覆盖内容。
SPEAKER_ENROLL_FILE = Path(
    os.environ.get(
        "QINGYUAN_SPEAKER_ENROLL",
        r"C:\MyAgent\data\speaker\enroll_0.wav",
    )
)


# ============================================================
# 全局状态
# ============================================================

cancel_event = threading.Event()
listen_lock = threading.Lock()

pyaudio_instance = None
mic_device_index = None
mic_device_name = ""

sensevoice_model = None
speaker_pipeline = None


# ============================================================
# 基础工具
# ============================================================

def _resolve_microphone():
    global pyaudio_instance
    global mic_device_index
    global mic_device_name

    pyaudio_instance = pyaudio.PyAudio()

    if MIC_DEVICE_ENV:
        mic_device_index = int(MIC_DEVICE_ENV)
        info = pyaudio_instance.get_device_info_by_index(
            mic_device_index
        )
    else:
        info = pyaudio_instance.get_default_input_device_info()
        mic_device_index = int(info["index"])

    mic_device_name = str(info.get("name", ""))

    if int(info.get("maxInputChannels", 0)) < 1:
        raise RuntimeError(
            f"输入设备不可用：{mic_device_index} {mic_device_name}"
        )


def _pcm_rms_normalized(audio_bytes: bytes) -> float:
    if not audio_bytes:
        return 0.0

    samples = np.frombuffer(
        audio_bytes,
        dtype=np.int16,
    ).astype(np.float32)

    if samples.size == 0:
        return 0.0

    rms = float(
        np.sqrt(
            np.mean(
                np.square(samples)
            )
        )
    )

    return rms / 32768.0


def _vad_is_speech(
    vad: webrtcvad.Vad,
    audio_bytes: bytes,
) -> bool:
    """
    对一个约 0.5 秒 PCM16 音频块进行 WebRTC VAD。

    当前采用我们已经在 Fifine 上实测通过的 10ms frame，
    voiced frame 比例 > 50% 认为该 0.5 秒块包含有效语音。
    """
    frame_samples = int(
        AUDIO_RATE * VAD_FRAME_MS / 1000
    )
    frame_bytes = frame_samples * 2  # PCM16 = 2 bytes/sample

    voiced = 0
    total = 0

    for start in range(
        0,
        len(audio_bytes) - frame_bytes + 1,
        frame_bytes,
    ):
        frame = audio_bytes[
            start:start + frame_bytes
        ]

        total += 1

        if vad.is_speech(
            frame,
            sample_rate=AUDIO_RATE,
        ):
            voiced += 1

    if total == 0:
        return False

    return (
        voiced / total
        > VAD_SPEECH_RATIO
    )


def _write_temp_wav(audio_bytes: bytes) -> str:
    fd, path = tempfile.mkstemp(
        prefix="qingyuan_stt_",
        suffix=".wav",
    )
    os.close(fd)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(AUDIO_RATE)
        wf.writeframes(audio_bytes)

    return path


def _strip_sensevoice_tags(text: str) -> str:
    value = str(text or "").strip()

    # 例如：
    # <|zh|><|NEUTRAL|><|Speech|><|woitn|>清缘你好
    value = re.sub(
        r"<\|[^>]*\|>",
        "",
        value,
    )

    return value.strip()


def _chinese_char_positions(text: str):
    chars = []
    positions = []

    for index, char in enumerate(text):
        if "\u4e00" <= char <= "\u9fff":
            chars.append(char)
            positions.append(index)

    return chars, positions


def _find_wake_span_by_pinyin(text: str):
    """
    用拼音而不是固定汉字判断“清渊”。

    清渊 / 清缘 / 清源 / 庆愿 等，只要两字拼音为
    qing yuan，就视为唤醒词。
    """
    chars, positions = _chinese_char_positions(
        text
    )

    if len(chars) < 2:
        return None

    syllables = [
        item[0]
        for item in pinyin(
            "".join(chars),
            style=Style.NORMAL,
        )
    ]

    for index in range(
        len(syllables) - 1
    ):
        if (
            syllables[index] == WAKE_PINYIN[0]
            and syllables[index + 1] == WAKE_PINYIN[1]
        ):
            start = positions[index]
            end = positions[index + 1] + 1
            return start, end

    return None


def _canonicalize_wake_word(text: str):
    span = _find_wake_span_by_pinyin(text)

    if span is None:
        return False, text

    start, end = span

    canonical = (
        text[:start]
        + "清渊"
        + text[end:]
    )

    return True, canonical


def stop_tts_playback():
    try:
        with urlopen(
            TTS_STOP_URL,
            timeout=1.0,
        ) as response:
            response.read()
    except Exception:
        pass


# ============================================================
# 模型加载
# ============================================================

def load_models():
    global sensevoice_model
    global speaker_pipeline

    print("=" * 60)
    print("正在启动清渊新版语音系统……")
    print(
        "语音架构：WebRTC VAD -> SenseVoiceSmall"
        " -> 拼音唤醒 -> CAM++"
    )

    print()
    print("正在加载 SenseVoiceSmall……")

    sensevoice_model = AutoModel(
        model=SENSEVOICE_MODEL,
        trust_remote_code=True,
        disable_update=True,
    )

    print("SenseVoiceSmall 加载完成")

    if SPEAKER_VERIFY_ENABLED:
        print()
        print("正在加载 CAM++ 声纹模型……")

        speaker_pipeline = pipeline(
            task="speaker-verification",
            model=SPEAKER_MODEL,
            model_revision=SPEAKER_MODEL_REVISION,
        )

        print("CAM++ 声纹模型加载完成")
    else:
        print()
        print("⚠ CAM++ 声纹验证已通过环境变量关闭")

    print("=" * 60)


# ============================================================
# 录制一句话
# ============================================================

def record_one_utterance(
    barge_in: bool = False,
):
    cancel_event.clear()

    vad = webrtcvad.Vad()
    vad.set_mode(VAD_MODE)

    stream = pyaudio_instance.open(
        format=AUDIO_FORMAT,
        channels=AUDIO_CHANNELS,
        rate=AUDIO_RATE,
        input=True,
        input_device_index=mic_device_index,
        frames_per_buffer=CHUNK,
    )

    audio_buffer = []
    previous_blocks = []
    recorded_blocks = []

    speech_started = False
    last_active_time = time.time()
    speech_start_time = None

    print()
    if barge_in:
        print("🎤 清渊正在监听打断……")
    else:
        print("🎤 清渊正在听……")

    try:
        while True:
            if cancel_event.is_set():
                return None, True

            data = stream.read(
                CHUNK,
                exception_on_overflow=False,
            )

            audio_buffer.append(data)

            buffered_seconds = (
                len(audio_buffer)
                * CHUNK
                / AUDIO_RATE
            )

            if (
                buffered_seconds
                < VAD_WINDOW_SECONDS
            ):
                continue

            raw_audio = b"".join(
                audio_buffer
            )
            audio_buffer = []

            vad_active = _vad_is_speech(
                vad,
                raw_audio,
            )

            # 打断模式只在 VAD 之外加一个轻量 RMS 门槛，
            # 防止普通扬声器漏音过于容易打断清渊自己。
            if (
                barge_in
                and vad_active
                and _pcm_rms_normalized(raw_audio)
                < BARGE_MIN_RMS
            ):
                vad_active = False

            if vad_active:
                if not speech_started:
                    speech_started = True
                    speech_start_time = time.time()

                    if previous_blocks:
                        recorded_blocks.extend(
                            previous_blocks[-PRE_ROLL_BLOCKS:]
                        )

                    print("🟢 检测到语音活动")

                    if barge_in:
                        print(
                            "⏹ 检测到用户打断，停止当前 TTS"
                        )
                        stop_tts_playback()

                recorded_blocks.append(
                    raw_audio
                )
                last_active_time = time.time()

            else:
                if not speech_started:
                    previous_blocks.append(
                        raw_audio
                    )

                    if (
                        len(previous_blocks)
                        > PRE_ROLL_BLOCKS
                    ):
                        previous_blocks = (
                            previous_blocks[
                                -PRE_ROLL_BLOCKS:
                            ]
                        )
                else:
                    # 说话已经开始后，保留短暂停顿块，
                    # 避免一句话内部较轻的字被裁掉。
                    recorded_blocks.append(
                        raw_audio
                    )

            if speech_started:
                now = time.time()

                if (
                    now - last_active_time
                    >= NO_SPEECH_THRESHOLD
                ):
                    print("🔴 检测到停顿")
                    break

                if (
                    speech_start_time is not None
                    and now - speech_start_time
                    >= MAX_RECORD_SECONDS
                ):
                    print("🔴 达到最长录音时间")
                    break

    finally:
        stream.stop_stream()
        stream.close()

    if not recorded_blocks:
        return None, False

    audio_bytes = b"".join(
        recorded_blocks
    )

    duration = (
        len(audio_bytes)
        / 2
        / AUDIO_RATE
    )

    print(
        "录音时长：",
        round(duration, 2),
        "秒",
    )

    return audio_bytes, False


# ============================================================
# SenseVoice
# ============================================================

def transcribe_audio_file(
    audio_file: str,
) -> str:
    if cancel_event.is_set():
        return ""

    print("正在进行 SenseVoice 识别……")
    start_time = time.time()

    result = sensevoice_model.generate(
        input=audio_file,
        cache={},
        language="auto",
        use_itn=False,
    )

    if not result:
        return ""

    text = _strip_sensevoice_tags(
        result[0].get(
            "text",
            "",
        )
    )

    print("SenseVoice 结果：", text)
    print(
        "识别耗时：",
        round(
            time.time() - start_time,
            2,
        ),
        "秒",
    )

    return text


# ============================================================
# CAM++ 声纹
# ============================================================

def verify_speaker(
    audio_file: str,
):
    if not SPEAKER_VERIFY_ENABLED:
        return True, None

    if speaker_pipeline is None:
        print("🔴 CAM++ 尚未加载")
        return False, None

    if not SPEAKER_ENROLL_FILE.is_file():
        print(
            "🔴 找不到声纹注册文件：",
            SPEAKER_ENROLL_FILE,
        )
        return False, None

    if cancel_event.is_set():
        return False, None

    try:
        result = speaker_pipeline(
            [
                str(SPEAKER_ENROLL_FILE),
                audio_file,
            ],
            thr=SPEAKER_THRESHOLD,
        )

        score = result.get(
            "score",
            None,
        )
        verdict = str(
            result.get(
                "text",
                "",
            )
        ).lower()

        print(
            "CAM++ 声纹：",
            result,
        )

        passed = (
            verdict == "yes"
            and (
                score is None
                or float(score)
                >= SPEAKER_THRESHOLD
            )
        )

        if passed:
            print("🟢 声纹通过：确认是本人")
        else:
            print("🔴 声纹拒绝：非注册用户")

        return passed, score

    except Exception as exc:
        print(
            "🔴 CAM++ 声纹验证失败：",
            exc,
        )
        return False, None


# ============================================================
# 一次完整监听
# ============================================================

def process_one_utterance(
    standby: bool,
    barge_in: bool,
):
    audio_bytes, cancelled = (
        record_one_utterance(
            barge_in=barge_in,
        )
    )

    if cancelled:
        return {
            "text": "",
            "cancelled": True,
            "wake_detected": False,
            "speaker_verified": False,
            "speaker_score": None,
        }

    if not audio_bytes:
        return {
            "text": "",
            "cancelled": False,
            "wake_detected": False,
            "speaker_verified": False,
            "speaker_score": None,
        }

    temp_wav = _write_temp_wav(
        audio_bytes
    )

    try:
        text = transcribe_audio_file(
            temp_wav
        )

        if not text:
            return {
                "text": "",
                "cancelled": False,
                "wake_detected": False,
                "speaker_verified": False,
                "speaker_score": None,
            }

        wake_detected, canonical_text = (
            _canonicalize_wake_word(
                text
            )
        )

        if wake_detected:
            print(
                "🔵 拼音唤醒成功：",
                canonical_text,
            )

        # 待机状态严格执行：
        # ASR -> 拼音 KWS -> CAM++
        # 没有 qing yuan 就不把文本交给 Agent，
        # 防止旧 wake.py 的别名逻辑绕过声纹验证。
        if standby and not wake_detected:
            print(
                "⚪ 待机忽略：未检测到 qing yuan"
            )
            return {
                "text": "",
                "cancelled": False,
                "wake_detected": False,
                "speaker_verified": False,
                "speaker_score": None,
            }

        speaker_ok, speaker_score = (
            verify_speaker(
                temp_wav
            )
        )

        if not speaker_ok:
            return {
                "text": "",
                "cancelled": False,
                "wake_detected": wake_detected,
                "speaker_verified": False,
                "speaker_score": speaker_score,
            }

        return {
            "text": canonical_text,
            "cancelled": False,
            "wake_detected": wake_detected,
            "speaker_verified": True,
            "speaker_score": speaker_score,
        }

    finally:
        try:
            os.remove(
                temp_wav
            )
        except Exception:
            pass


# ============================================================
# HTTP
# ============================================================

class QingyuanSTTHandler(
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
        parsed = urlparse(
            self.path
        )
        path = parsed.path
        params = parse_qs(
            parsed.query
        )

        if path == "/health":
            self.send_json(
                200,
                {
                    "ok": True,
                    "name": "清渊 STT",
                    "engine": "SenseVoiceSmall",
                    "vad": "WebRTC VAD 2.0.10",
                    "speaker_verification": (
                        "CAM++"
                        if SPEAKER_VERIFY_ENABLED
                        else "disabled"
                    ),
                    "speaker_enrolled": (
                        SPEAKER_ENROLL_FILE.is_file()
                    ),
                    "speaker_threshold": (
                        SPEAKER_THRESHOLD
                    ),
                    "mic_device_index": (
                        mic_device_index
                    ),
                    "mic_device_name": (
                        mic_device_name
                    ),
                },
            )
            return

        if path == "/cancel":
            cancel_event.set()
            self.send_json(
                200,
                {
                    "ok": True,
                    "cancelled": True,
                },
            )
            return

        if path == "/shutdown":
            cancel_event.set()
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

        if path == "/listen":
            barge_in = (
                params.get(
                    "barge",
                    ["0"],
                )[0]
                == "1"
            )

            standby = (
                params.get(
                    "standby",
                    ["0"],
                )[0]
                == "1"
            )

            if not listen_lock.acquire(
                blocking=False
            ):
                self.send_json(
                    409,
                    {
                        "ok": False,
                        "error": "already listening",
                    },
                )
                return

            try:
                result = process_one_utterance(
                    standby=standby,
                    barge_in=barge_in,
                )

                self.send_json(
                    200,
                    {
                        "ok": True,
                        **result,
                    },
                )

            except Exception as exc:
                print(
                    "语音识别失败：",
                    repr(exc),
                )

                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                )

            finally:
                listen_lock.release()

            return

        self.send_json(
            404,
            {
                "ok": False,
                "error": "Not found",
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

def main():
    _resolve_microphone()
    load_models()

    print()
    print(
        "当前麦克风：",
        f"[{mic_device_index}]",
        mic_device_name,
    )

    if SPEAKER_VERIFY_ENABLED:
        if SPEAKER_ENROLL_FILE.is_file():
            print(
                "声纹注册文件：",
                SPEAKER_ENROLL_FILE,
            )
        else:
            print(
                "⚠ 尚未找到声纹注册文件：",
                SPEAKER_ENROLL_FILE,
            )

    server = ThreadingHTTPServer(
        (HOST, PORT),
        QingyuanSTTHandler,
    )

    print()
    print("=" * 60)
    print("清渊新版语音识别服务已启动")
    print(f"http://{HOST}:{PORT}")
    print("普通监听：/listen")
    print("待机唤醒：/listen?standby=1")
    print("打断监听：/listen?barge=1")
    print("取消接口：/cancel")
    print("关闭接口：/shutdown")
    print("=" * 60)

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print()
        print("清渊语音识别服务已关闭。")

    finally:
        cancel_event.set()

        try:
            server.server_close()
        except Exception:
            pass

        try:
            if pyaudio_instance is not None:
                pyaudio_instance.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
