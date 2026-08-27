import json
import os
import re
import threading
import time
from difflib import SequenceMatcher
from collections import deque
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from urllib.parse import urlparse, parse_qs

import numpy as np
import sounddevice as sd

from faster_whisper import WhisperModel

# Voice Core 2.0 可选依赖。
# 未安装时自动回退到原有 Whisper + RMS，不影响清渊启动。
try:
    import webrtcvad
except Exception:
    webrtcvad = None

try:
    from pypinyin import pinyin, Style
except Exception:
    pinyin = None
    Style = None

try:
    from funasr import AutoModel as FunASRAutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
except Exception:
    FunASRAutoModel = None
    rich_transcription_postprocess = None


# ============================================================
# 配置
# ============================================================

HOST = "127.0.0.1"
PORT = 8766

SAMPLE_RATE = 16000
CHANNELS = 1

MIC_DEVICE = 1

BLOCK_DURATION = 0.02
BLOCK_SIZE = int(
    SAMPLE_RATE * BLOCK_DURATION
)

PRE_ROLL_SECONDS = 0.60
END_SILENCE_SECONDS = 1.10
MAX_RECORD_SECONDS = 30

CALIBRATION_SECONDS = 1.0

# 连续对话中，清渊正在说话时用于强制打断。
# 因为音箱声音也可能漏进麦克风，所以打断阈值比普通监听高。
BARGE_THRESHOLD_MULTIPLIER = 3.0

TTS_STOP_URL = "http://127.0.0.1:8765/stop"

# Whisper 模型保持可配置。默认仍使用当前稳定的 small + CPU INT8，
# 这样本次精度升级不会突然改变你的硬件负载。
# 以后有合适的 NVIDIA GPU 时，可通过环境变量切换：
# QINGYUAN_STT_MODEL=turbo
# QINGYUAN_STT_DEVICE=cuda
# QINGYUAN_STT_COMPUTE_TYPE=float16
STT_MODEL_NAME = os.environ.get(
    "QINGYUAN_STT_MODEL",
    "small",
).strip() or "small"

STT_DEVICE = os.environ.get(
    "QINGYUAN_STT_DEVICE",
    "cpu",
).strip() or "cpu"

STT_COMPUTE_TYPE = os.environ.get(
    "QINGYUAN_STT_COMPUTE_TYPE",
    "int8",
).strip() or "int8"


# Voice Core 2.0
# auto: SenseVoice 可用则优先，否则 Whisper。
# whisper: 强制只用 faster-whisper。
# sensevoice: 优先 SenseVoice，失败仍会回退 Whisper。
ASR_ENGINE = os.environ.get(
    "QINGYUAN_ASR_ENGINE",
    "auto",
).strip().lower() or "auto"

SENSEVOICE_MODEL = os.environ.get(
    "QINGYUAN_SENSEVOICE_MODEL",
    "iic/SenseVoiceSmall",
).strip() or "iic/SenseVoiceSmall"

SENSEVOICE_DEVICE = os.environ.get(
    "QINGYUAN_SENSEVOICE_DEVICE",
    "cpu",
).strip() or "cpu"

WEBRTC_VAD_MODE = int(os.environ.get(
    "QINGYUAN_WEBRTC_VAD_MODE",
    "3",
))

# Voice Core 2.0 Sensitivity Rebalance: 待机仍比连续对话严格，但不再使用过高固定 RMS 下限。
# WebRTC VAD 只负责判断“像不像人声”，再叠加 RMS 能量门控，
# 避免键盘、桌面碰撞、风扇和扬声器漏音频繁触发录音，同时保留正常说话灵敏度。
STANDBY_MIN_RMS = float(os.environ.get(
    "QINGYUAN_STANDBY_MIN_RMS",
    "0.0035",
))
ACTIVE_MIN_RMS = float(os.environ.get(
    "QINGYUAN_ACTIVE_MIN_RMS",
    "0.0025",
))
BARGE_MIN_THRESHOLD = float(os.environ.get(
    "QINGYUAN_BARGE_MIN_RMS",
    "0.012",
))

STANDBY_START_CONFIRM_SECONDS = 0.26
ACTIVE_START_CONFIRM_SECONDS = 0.14
BARGE_CONFIRM_SECONDS = 0.24

STANDBY_START_RATIO = 0.65
ACTIVE_START_RATIO = 0.55
BARGE_START_RATIO = 0.72
WEBRTC_END_RATIO = 0.18
WAKE_PINYIN_THRESHOLD = 0.76
WAKE_PINYIN_TARGET = ("qing", "yuan")

PRIMARY_BEAM_SIZE = 5
RETRY_BEAM_SIZE = 8
LOW_CONFIDENCE_LOGPROB = -0.72
HIGH_NO_SPEECH_PROB = 0.55
RECENT_TRANSCRIPT_LIMIT = 3
SHORT_UTTERANCE_RETRY_CHARS = 14

NO_RETRY_SHORT_PHRASES = {
    "在吗",
    "好的",
    "可以",
    "同意",
    "取消",
    "停止",
    "谢谢",
}

# 待机唤醒近音字符集合。
# Whisper 常把“清渊”识别成：青云、轻冤、情愿、请愿等。
WAKE_FIRST_CHARS = set(
    "清青轻輕情请請倾傾卿"
)

WAKE_SECOND_CHARS = set(
    "渊淵源原元园園愿願冤云雲员員圆圓袁缘緣援"
)



# ============================================================
# 用户语音词库 / 专有名词纠错
# ============================================================

STT_VOCAB_FILE = Path(
    r"C:\MyAgent\data\stt_vocabulary.json"
)

DEFAULT_STT_VOCAB = {
    "明日方舟": [
        "名誉放桌",
        "名譽放桌",
        "明日放周",
        "明日放桌",
        "明日方周",
        "名誉方舟",
    ],
    "清渊": [
        "青元",
        "清元",
        "请元",
        "請元",
        "请愿",
        "請願",
        "青云",
        "青雲",
        "清淵",
    ],
    "Chrome": [
        "克罗姆",
        "谷歌浏览器",
    ],
    "浏览器": [
        "楼览器",
        "樓覽器",
        "游览器",
        "浏揽器",
    ],
    "微信": [
        "威信",
    ],
}


def ensure_stt_vocabulary():

    try:

        STT_VOCAB_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not STT_VOCAB_FILE.exists():

            STT_VOCAB_FILE.write_text(
                json.dumps(
                    DEFAULT_STT_VOCAB,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    except Exception:
        pass


def load_stt_vocabulary():

    ensure_stt_vocabulary()

    try:

        data = json.loads(
            STT_VOCAB_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return DEFAULT_STT_VOCAB


def vocabulary_prompt():

    vocab = load_stt_vocabulary()

    canonical = [
        str(key)
        for key in vocab.keys()
    ]

    if not canonical:
        return ""

    return (
        "关键词："
        + "，".join(canonical[:30])
    )


def vocabulary_hotwords():

    vocab = load_stt_vocabulary()

    words = [
        "清渊",
        *[
            str(key).strip()
            for key in vocab.keys()
            if str(key).strip()
        ],
    ]

    # 去重并限制长度，避免把 hotwords 变成超长上下文。
    unique = []
    seen = set()

    for word in words:
        if word in seen:
            continue
        seen.add(word)
        unique.append(word)

    return "，".join(unique[:40])


def apply_transcript_corrections(
    text: str
) -> str:

    result = str(text).strip()

    if not result:
        return result

    # --------------------------------------------
    # 整句级纠错：
    # 只对非常短、非常明确的常见语音漂移生效。
    # --------------------------------------------

    compact = (
        result
        .strip()
        .strip("。！!？，, ")
    )

    exact_utterance_map = {
        "再马": "在吗",
        "再馬": "在吗",
        "再麻": "在吗",
        "在嘛": "在吗",
        "在么": "在吗",
        "同一": "同意",
        "统一": "同意",
        "統一": "同意",
    }

    if compact in exact_utterance_map:

        return exact_utterance_map[
            compact
        ]

    vocab = load_stt_vocabulary()

    for canonical, aliases in vocab.items():

        canonical = str(canonical)

        if not isinstance(
            aliases,
            list,
        ):
            continue

        for alias in aliases:

            alias = str(alias).strip()

            if (
                alias
                and alias in result
            ):

                result = result.replace(
                    alias,
                    canonical,
                )

    # 浏览器常见近音
    browser_aliases = {
        "楼览器": "浏览器",
        "樓覽器": "浏览器",
        "游览器": "浏览器",
        "浏揽器": "浏览器",
    }

    for alias, canonical in (
        browser_aliases.items()
    ):

        result = result.replace(
            alias,
            canonical,
        )

    return result


# ============================================================
# 全局状态
# ============================================================

cancel_event = threading.Event()
listen_lock = threading.Lock()

speech_threshold = 0.008
recent_transcripts = deque(maxlen=RECENT_TRANSCRIPT_LIMIT)

webrtc_vad = None
if webrtcvad is not None:
    try:
        webrtc_vad = webrtcvad.Vad(
            max(0, min(3, WEBRTC_VAD_MODE))
        )
    except Exception:
        webrtc_vad = None

sensevoice_model = None


# ============================================================
# ASR engines: SenseVoice + Whisper fallback
# ============================================================

print("=" * 60)
print("正在加载清渊 Voice Core 2.0……")

model = WhisperModel(
    STT_MODEL_NAME,
    device=STT_DEVICE,
    compute_type=STT_COMPUTE_TYPE,
)

print(
    "Whisper fallback：",
    STT_MODEL_NAME,
    "| device:",
    STT_DEVICE,
    "| compute:",
    STT_COMPUTE_TYPE,
)

sensevoice_state = "disabled"

if ASR_ENGINE in {"auto", "sensevoice", "hybrid"}:
    if FunASRAutoModel is None:
        sensevoice_state = "missing_dependency"
        print(
            "[Voice Core] 未安装 FunASR/SenseVoice，"
            "当前先使用 Whisper fallback。"
        )
    else:
        sensevoice_state = "pending"
        print(
            "SenseVoice 将在 STT 服务启动后后台加载，"
            "首次运行可自动下载模型。"
        )


def _load_sensevoice_background():
    global sensevoice_model, sensevoice_state

    if sensevoice_state != "pending":
        return

    sensevoice_state = "loading"

    try:
        print(
            "[Voice Core] 后台加载 SenseVoice：",
            SENSEVOICE_MODEL,
        )
        loaded = FunASRAutoModel(
            model=SENSEVOICE_MODEL,
            trust_remote_code=True,
            device=SENSEVOICE_DEVICE,
        )
        sensevoice_model = loaded
        sensevoice_state = "ready"
        print("[Voice Core] SenseVoice 加载成功，已切换为双引擎。")
    except Exception as exc:
        sensevoice_model = None
        sensevoice_state = "error"
        print(
            "[Voice Core] SenseVoice 加载失败，"
            "继续使用 Whisper：",
            type(exc).__name__,
            exc,
        )


print(
    "WebRTC VAD：",
    "enabled" if webrtc_vad is not None else "fallback-rms",
)
print(
    "拼音唤醒：",
    "enabled" if pinyin is not None else "fallback-char",
)
print("清渊 Voice Core 2.0 加载完成")
print("=" * 60)


mic_info = sd.query_devices(
    MIC_DEVICE,
    kind="input",
)

print(
    "当前麦克风：",
    mic_info["name"]
)


# ============================================================
# 音量
# ============================================================

def calculate_rms(audio):

    if len(audio) == 0:
        return 0.0

    return float(
        np.sqrt(
            np.mean(
                np.square(audio)
            )
        )
    )


# ============================================================
# Voice activity detection
# ============================================================

def _float_audio_to_pcm16(audio):
    clipped = np.clip(
        np.asarray(audio, dtype=np.float32),
        -1.0,
        1.0,
    )
    return (
        clipped * 32767.0
    ).astype(np.int16).tobytes()


def _frame_is_voice(
    audio,
    *,
    standby=False,
    barge_in=False,
):
    rms = calculate_rms(audio)

    if barge_in:
        energy_threshold = max(
            speech_threshold * BARGE_THRESHOLD_MULTIPLIER,
            BARGE_MIN_THRESHOLD,
        )
    elif standby:
        energy_threshold = max(
            speech_threshold * 1.45,
            STANDBY_MIN_RMS,
        )
    else:
        energy_threshold = max(
            speech_threshold * 1.10,
            ACTIVE_MIN_RMS,
        )

    # 双门控：必须先达到能量门槛，再由 WebRTC 判断是否像人声。
    # 这样可以明显降低键盘、鼠标、桌面震动和远处音箱声误触发。
    if rms < energy_threshold:
        return False

    if webrtc_vad is not None:
        try:
            return bool(
                webrtc_vad.is_speech(
                    _float_audio_to_pcm16(audio),
                    SAMPLE_RATE,
                )
            )
        except Exception:
            pass

    return True


def _voice_window_ratio(history):
    if not history:
        return 0.0
    return sum(1 for x in history if x) / len(history)


# ============================================================
# 启动时校准一次环境噪声
# ============================================================

def calibrate_noise():

    global speech_threshold

    print()
    print("正在进行启动环境噪声校准……")
    print("请保持安静约 1 秒。")

    noise_values = []

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        device=MIC_DEVICE,
        blocksize=BLOCK_SIZE,
    ) as stream:

        blocks = int(
            CALIBRATION_SECONDS
            / BLOCK_DURATION
        )

        for _ in range(blocks):

            block, _ = stream.read(
                BLOCK_SIZE
            )

            audio = (
                block[:, 0]
                .copy()
            )

            noise_values.append(
                calculate_rms(audio)
            )

    noise_rms = float(
        np.mean(noise_values)
    )

    speech_threshold = max(
        noise_rms * 8.0,
        0.0025,
    )

    print(
        "环境底噪：",
        round(noise_rms, 5)
    )

    print(
        "语音触发阈值：",
        round(speech_threshold, 5)
    )

    print(
        "待机实际能量门槛：",
        round(
            max(
                speech_threshold * 1.45,
                STANDBY_MIN_RMS,
            ),
            5,
        )
    )

    print(
        "连续对话实际能量门槛：",
        round(
            max(
                speech_threshold * 1.10,
                ACTIVE_MIN_RMS,
            ),
            5,
        )
    )


# ============================================================
# 强制停止当前 TTS
# ============================================================

def stop_tts_playback():

    try:

        with urlopen(
            TTS_STOP_URL,
            timeout=1,
        ) as response:

            response.read()

    except Exception:
        pass


# ============================================================
# 录制一句话
# ============================================================

def record_one_utterance(
    standby: bool = False,
    barge_in: bool = False,
):

    cancel_event.clear()

    pre_roll_blocks = max(
        1,
        int(PRE_ROLL_SECONDS / BLOCK_DURATION),
    )
    if barge_in:
        start_confirm_seconds = BARGE_CONFIRM_SECONDS
        start_ratio = BARGE_START_RATIO
    elif standby:
        start_confirm_seconds = STANDBY_START_CONFIRM_SECONDS
        start_ratio = STANDBY_START_RATIO
    else:
        start_confirm_seconds = ACTIVE_START_CONFIRM_SECONDS
        start_ratio = ACTIVE_START_RATIO

    window_blocks = max(
        3,
        int(start_confirm_seconds / BLOCK_DURATION),
    )

    pre_buffer = deque(maxlen=pre_roll_blocks)
    voice_history = deque(maxlen=window_blocks)
    recorded_blocks = []

    speech_started = False
    speech_start_time = None
    last_voice_time = None

    print()
    print("🎤 清渊正在听……")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        device=MIC_DEVICE,
        blocksize=BLOCK_SIZE,
    ) as stream:

        while True:
            if cancel_event.is_set():
                return None, True

            block, _ = stream.read(BLOCK_SIZE)
            audio = block[:, 0].copy()
            is_voice = _frame_is_voice(
                audio,
                standby=standby,
                barge_in=barge_in,
            )

            voice_history.append(is_voice)

            if not speech_started:
                pre_buffer.append(audio)

                if (
                    len(voice_history) >= window_blocks
                    and _voice_window_ratio(voice_history)
                    >= start_ratio
                ):
                    speech_started = True
                    now = time.time()
                    speech_start_time = now
                    last_voice_time = now
                    recorded_blocks.extend(list(pre_buffer))
                    print("🟢 WebRTC VAD 检测到说话")

                    if barge_in:
                        print(
                            "⏹ 检测到用户打断，停止清渊当前播报"
                        )
                        stop_tts_playback()

            else:
                recorded_blocks.append(audio)

                if is_voice:
                    last_voice_time = time.time()

                # 既看最近窗口，也看持续静音时间。
                # 能比纯 RMS 更快结束，同时减少键盘/桌面噪声误判。
                quiet_ratio = (
                    _voice_window_ratio(voice_history)
                    <= WEBRTC_END_RATIO
                )
                silence_duration = (
                    time.time() - last_voice_time
                )

                if (
                    quiet_ratio
                    and silence_duration >= END_SILENCE_SECONDS
                ):
                    print("🔴 WebRTC VAD 检测到停顿")
                    break

                if (
                    time.time() - speech_start_time
                    >= MAX_RECORD_SECONDS
                ):
                    print("🔴 达到最长录音时间")
                    break

    if not recorded_blocks:
        return None, False

    audio_data = np.concatenate(recorded_blocks)

    print(
        "录音时长：",
        round(len(audio_data) / SAMPLE_RATE, 2),
        "秒",
    )

    return audio_data, False


# ============================================================
# ASR / Hybrid 转录
# ============================================================

def _normalize_for_dedupe(text: str) -> str:
    return (
        str(text)
        .strip()
        .strip("。！!？，,；;：: ")
        .lower()
    )


def _collapse_repeated_phrase(text: str) -> str:
    raw = str(text).strip()

    if not raw:
        return raw

    pieces = [
        piece.strip()
        for piece in re.split(r"[。！？!?；;]+", raw)
        if piece.strip()
    ]

    if len(pieces) > 1:
        deduped = []

        for piece in pieces:
            if (
                not deduped
                or _normalize_for_dedupe(piece)
                != _normalize_for_dedupe(deduped[-1])
            ):
                deduped.append(piece)

        raw = "。".join(deduped)

    compact = _normalize_for_dedupe(raw)
    length = len(compact)

    if length >= 2 and length % 2 == 0:
        half = length // 2
        if compact[:half] == compact[half:]:
            return compact[:half]

    return raw


def _segments_to_text(segments):
    text_parts = []
    last_normalized = ""

    for segment in segments:
        text = segment.text.strip()

        if not text:
            continue

        normalized = _normalize_for_dedupe(text)

        if normalized and normalized == last_normalized:
            continue

        text_parts.append(text)
        last_normalized = normalized

    combined = "".join(text_parts).strip()

    return _collapse_repeated_phrase(combined)


def _find_wake_span(text: str):
    """Return the character span of a likely Qingyuan wake word, or None.

    The pinyin matcher keeps the original character positions so a confirmed
    near-homophone such as 庭缘/庆元 can be repaired to 清渊 without replacing
    the rest of the transcript.
    """
    normalized = str(text)

    exact_index = normalized.find("清渊")
    if exact_index != -1:
        return exact_index, exact_index + 2

    # Zero-dependency character fallback.
    for index in range(len(normalized) - 1):
        first = normalized[index]
        second = normalized[index + 1]
        if (
            first in WAKE_FIRST_CHARS
            and second in WAKE_SECOND_CHARS
        ):
            return index, index + 2

    if pinyin is None or Style is None:
        return None

    try:
        chars = []
        positions = []
        for index, char in enumerate(normalized):
            if "\u4e00" <= char <= "\u9fff":
                chars.append(char)
                positions.append(index)

        if len(chars) < 2:
            return None

        syllables = [
            item[0].lower()
            for item in pinyin(
                "".join(chars),
                style=Style.NORMAL,
                errors="ignore",
            )
            if item
        ]

        if len(syllables) != len(chars):
            return None

        target = "".join(WAKE_PINYIN_TARGET)

        for i in range(len(syllables) - 1):
            pair = "".join(syllables[i:i + 2])
            score = SequenceMatcher(
                None,
                pair,
                target,
            ).ratio()

            if score >= WAKE_PINYIN_THRESHOLD:
                return positions[i], positions[i + 1] + 1

    except Exception:
        return None

    return None


def _contains_wake_pattern(text: str) -> bool:
    return _find_wake_span(text) is not None


def _canonicalize_confirmed_wake(text: str) -> str:
    """Repair only the confirmed wake-word span; never rewrite the command."""
    raw = str(text).strip()
    span = _find_wake_span(raw)
    if span is None:
        return raw

    start, end = span
    return raw[:start] + "清渊" + raw[end:]


def _fuse_primary_with_whisper_wake(
    primary_text: str,
    whisper_text: str,
) -> str:
    """Use SenseVoice as the sentence source and Whisper only as wake proof.

    This prevents a good SenseVoice content word (e.g. 雨伞) from being
    overwritten by a poorer Whisper whole-sentence hypothesis (e.g. 语散)
    just because Whisper happened to spell 清渊 correctly.
    """
    primary = str(primary_text).strip()
    whisper = str(whisper_text).strip()

    if not primary:
        if _contains_wake_pattern(whisper):
            return _canonicalize_confirmed_wake(whisper)
        return whisper

    # Only canonicalize the wake span when both engines independently hear a
    # wake-like two-syllable phrase. The rest of SenseVoice is preserved.
    if (
        _contains_wake_pattern(primary)
        and _contains_wake_pattern(whisper)
    ):
        return _canonicalize_confirmed_wake(primary)

    return primary


def _remember_transcript(text: str):
    cleaned = str(text).strip()
    if not cleaned:
        return

    normalized = _normalize_for_dedupe(cleaned)

    if recent_transcripts:
        previous = _normalize_for_dedupe(
            recent_transcripts[-1]
        )
        if normalized == previous:
            return

    recent_transcripts.append(cleaned)


def _recent_context_prompt():
    if not recent_transcripts:
        return ""

    recent = "；".join(
        list(recent_transcripts)[-RECENT_TRANSCRIPT_LIMIT:]
    )

    # 只给少量近期上下文，避免旧句子反过来污染识别。
    return (
        "最近对话参考："
        + recent[:120]
        + "。"
    )


def _build_initial_prompt(
    standby: bool,
    strong: bool,
):
    if standby:
        base = (
            "以下是简体中文普通话语音。"
            "句首可能真实出现名字‘清渊’，也可能没有。"
            "请忠实转写实际听到的内容，不要自行添加唤醒词。"
        )
    else:
        base = (
            "以下是用户对本地智能体清渊说的简体中文普通话。"
            "请忠实转写，不要改写用户原意。"
        )

    if strong:
        base += (
            "请特别注意人名、软件名、游戏名、英文词和用户词库中的专有名词。"
        )

    return (
        base
        + vocabulary_prompt()
        + "。"
        + _recent_context_prompt()
    )


def _candidate_metrics(segments):
    logprobs = []
    no_speech_probs = []

    for segment in segments:
        avg_logprob = getattr(
            segment,
            "avg_logprob",
            None,
        )

        if avg_logprob is not None:
            try:
                logprobs.append(
                    float(avg_logprob)
                )
            except Exception:
                pass

        no_speech_prob = getattr(
            segment,
            "no_speech_prob",
            None,
        )

        if no_speech_prob is not None:
            try:
                no_speech_probs.append(
                    float(no_speech_prob)
                )
            except Exception:
                pass

    return {
        "avg_logprob": (
            sum(logprobs) / len(logprobs)
            if logprobs
            else None
        ),
        "max_no_speech_prob": (
            max(no_speech_probs)
            if no_speech_probs
            else None
        ),
    }


def _sensevoice_transcribe(audio_data):
    if sensevoice_model is None:
        return ""

    try:
        result = sensevoice_model.generate(
            input=np.asarray(
                audio_data,
                dtype=np.float32,
            ),
            cache={},
            language="zh",
            use_itn=True,
            batch_size_s=60,
        )

        if not result:
            return ""

        item = result[0]
        text = (
            item.get("text", "")
            if isinstance(item, dict)
            else str(item)
        )

        if rich_transcription_postprocess is not None:
            try:
                text = rich_transcription_postprocess(text)
            except Exception:
                pass

        # SenseVoice 可能保留语言/情绪/事件标签。
        text = re.sub(r"<\|[^|>]+\|>", "", str(text))
        return apply_transcript_corrections(text.strip())

    except Exception as exc:
        print(
            "[SenseVoice] 本次识别失败，转 Whisper：",
            type(exc).__name__,
            exc,
        )
        return ""


def _looks_suspicious(text: str) -> bool:
    normalized = _normalize_for_dedupe(text)
    if not normalized or len(normalized) <= 1:
        return True

    # 极端重复、标签残留或大量不可识别字符，交给 Whisper 复核。
    if "<|" in text or "|>" in text:
        return True
    if re.search(r"(.)\1{4,}", normalized):
        return True
    return False


def _hybrid_candidate(audio_data, *, standby: bool):
    if (
        ASR_ENGINE != "whisper"
        and sensevoice_model is not None
    ):
        text = _sensevoice_transcribe(audio_data)
        if text:
            print("SenseVoice 识别：", text)
            return text
    return ""


def _transcribe_candidate(
    audio_data,
    *,
    standby: bool,
    strong: bool,
    use_hotwords: bool,
):
    beam_size = (
        RETRY_BEAM_SIZE
        if strong
        else PRIMARY_BEAM_SIZE
    )

    kwargs = {
        "language": "zh",
        "task": "transcribe",
        "beam_size": beam_size,
        "temperature": 0,
        "without_timestamps": True,
        "condition_on_previous_text": False,
        # 录音层已经完成一次 VAD + 0.55 秒 pre-roll。
        # 这里不再进行第二次 VAD，避免句首“清渊”或短词再次被裁掉。
        "vad_filter": False,
        "initial_prompt": _build_initial_prompt(
            standby=standby,
            strong=strong,
        ),
    }

    if use_hotwords:
        hotwords = vocabulary_hotwords()
        if hotwords:
            kwargs["hotwords"] = hotwords

    segments, _ = model.transcribe(
        audio_data,
        **kwargs,
    )

    collected = list(segments)

    text = apply_transcript_corrections(
        _segments_to_text(collected)
    )

    metrics = _candidate_metrics(
        collected
    )

    return text, metrics


def _needs_retry(
    text: str,
    metrics: dict,
) -> bool:
    normalized = _normalize_for_dedupe(text)

    if not normalized:
        return True

    if len(normalized) <= 1:
        return True

    # 清渊的大部分语音命令都很短。短句一旦识错一个词，
    # 含义可能完全改变，因此在 balanced 精度模式下做一次强解码复核。
    if (
        len(normalized) <= SHORT_UTTERANCE_RETRY_CHARS
        and normalized not in NO_RETRY_SHORT_PHRASES
    ):
        return True

    avg_logprob = metrics.get(
        "avg_logprob"
    )

    if (
        avg_logprob is not None
        and avg_logprob < LOW_CONFIDENCE_LOGPROB
    ):
        return True

    no_speech_prob = metrics.get(
        "max_no_speech_prob"
    )

    if (
        no_speech_prob is not None
        and no_speech_prob > HIGH_NO_SPEECH_PROB
    ):
        return True

    return False


def _candidate_score(
    text: str,
    metrics: dict,
) -> float:
    if not text.strip():
        return -999.0

    avg_logprob = metrics.get(
        "avg_logprob"
    )

    no_speech_prob = metrics.get(
        "max_no_speech_prob"
    )

    score = (
        float(avg_logprob)
        if avg_logprob is not None
        else -1.0
    )

    if no_speech_prob is not None:
        score -= float(no_speech_prob) * 0.35

    # 很轻微地偏向信息更完整的候选，避免只剩一两个字的结果胜出。
    score += min(
        len(_normalize_for_dedupe(text)),
        40,
    ) * 0.002

    # 命中用户维护的专有词时给很小的奖励。
    # 只用于候选排序，不会强行把普通句子改成词库内容。
    for canonical in load_stt_vocabulary().keys():
        word = str(canonical).strip()
        if word and word in text:
            score += 0.02

    return score


def _choose_better_candidate(
    first_text,
    first_metrics,
    second_text,
    second_metrics,
):
    first_score = _candidate_score(
        first_text,
        first_metrics,
    )

    second_score = _candidate_score(
        second_text,
        second_metrics,
    )

    print(
        "识别候选评分：",
        round(first_score, 3),
        "/",
        round(second_score, 3),
    )

    if second_score > first_score:
        return second_text

    return first_text


def transcribe_audio(
    audio_data,
    standby: bool = False,
):

    if audio_data is None:
        return ""
    if cancel_event.is_set():
        return ""

    print("正在识别……")
    start_time = time.time()

    # --------------------------------------------------------
    # SenseVoice 作为中文主识别；Whisper 保留为可靠 fallback。
    # 待机时如果 SenseVoice 没抓到唤醒词，会自动让 Whisper
    # 再听一次，避免“清渊”被吞后整句话直接丢失。
    # --------------------------------------------------------
    sv_text = _hybrid_candidate(
        audio_data,
        standby=standby,
    )

    if standby:
        if sv_text and _contains_wake_pattern(sv_text):
            # 用 Whisper 强确认一次唤醒，降低环境误唤醒。
            whisper_text, _ = _transcribe_candidate(
                audio_data,
                standby=True,
                strong=True,
                use_hotwords=True,
            )
            print("Whisper 唤醒确认：", whisper_text)

            if (
                _contains_wake_pattern(whisper_text)
                or _contains_wake_pattern(sv_text)
                and SequenceMatcher(
                    None,
                    _normalize_for_dedupe(sv_text),
                    _normalize_for_dedupe(whisper_text),
                ).ratio() >= 0.65
            ):
                final_text = _fuse_primary_with_whisper_wake(
                    sv_text,
                    whisper_text,
                )
                _remember_transcript(final_text)
                print("待机判定：拼音/双引擎唤醒通过")
                print("识别结果：", final_text)
                print(
                    "识别耗时：",
                    round(time.time() - start_time, 2),
                    "秒",
                )
                return final_text

        # SenseVoice 没抓住“清渊”时给 Whisper 第二次机会。
        first_text, _ = _transcribe_candidate(
            audio_data,
            standby=True,
            strong=False,
            use_hotwords=False,
        )
        print("Whisper 待机识别：", first_text)

        if not _contains_wake_pattern(first_text):
            print("待机判定：未检测到‘清渊’拼音/近音")
            print(
                "识别耗时：",
                round(time.time() - start_time, 2),
                "秒",
            )
            return first_text

        second_text, _ = _transcribe_candidate(
            audio_data,
            standby=True,
            strong=True,
            use_hotwords=True,
        )
        print("Whisper 唤醒确认：", second_text)

        if not _contains_wake_pattern(second_text):
            print("待机判定：唤醒确认失败")
            return ""

        _remember_transcript(second_text)
        print("待机判定：Whisper 双确认通过")
        print("识别结果：", second_text)
        print(
            "识别耗时：",
            round(time.time() - start_time, 2),
            "秒",
        )
        return second_text

    # --------------------------------------------------------
    # 已唤醒 / 连续对话
    # --------------------------------------------------------
    if sv_text and not _looks_suspicious(sv_text):
        final_text = sv_text

        # 短指令对误一个字很敏感；用 Whisper 做轻量复核。
        if (
            len(_normalize_for_dedupe(sv_text))
            <= SHORT_UTTERANCE_RETRY_CHARS
        ):
            whisper_text, _ = _transcribe_candidate(
                audio_data,
                standby=False,
                strong=True,
                use_hotwords=True,
            )
            print("Whisper 短句复核：", whisper_text)

            # v5.7.3 双引擎融合规则：
            # SenseVoice 是正文主来源；Whisper 负责复核唤醒词和兜底。
            # 不能再因为 Whisper 恰好命中“清渊”就整句覆盖 SenseVoice，
            # 否则会把 SenseVoice 正确的“雨伞”覆盖成 Whisper 的“语散”。
            fused_text = _fuse_primary_with_whisper_wake(
                sv_text,
                whisper_text,
            )

            if fused_text != sv_text:
                print(
                    "双引擎融合：Whisper 确认唤醒词，"
                    "正文保留 SenseVoice"
                )

            final_text = fused_text

            # 只有 SenseVoice 几乎没有正文时才允许 Whisper 整句兜底。
            # 正常完整句子不再被 Whisper 全量覆盖。
            if (
                len(_normalize_for_dedupe(final_text)) <= 2
                and len(_normalize_for_dedupe(whisper_text))
                > len(_normalize_for_dedupe(final_text))
            ):
                final_text = whisper_text

        final_text = apply_transcript_corrections(final_text)
        _remember_transcript(final_text)
        print("识别结果：", final_text)
        print(
            "识别耗时：",
            round(time.time() - start_time, 2),
            "秒",
        )
        return final_text

    # SenseVoice 不可用/可疑时走 v5.4 的 Whisper 双解码逻辑。
    first_text, first_metrics = _transcribe_candidate(
        audio_data,
        standby=False,
        strong=False,
        use_hotwords=True,
    )
    final_text = first_text

    if _needs_retry(first_text, first_metrics):
        print("识别置信度不足，正在自动二次识别……")
        second_text, second_metrics = _transcribe_candidate(
            audio_data,
            standby=False,
            strong=True,
            use_hotwords=True,
        )
        final_text = _choose_better_candidate(
            first_text,
            first_metrics,
            second_text,
            second_metrics,
        )

    final_text = apply_transcript_corrections(final_text)

    if cancel_event.is_set():
        return ""

    _remember_transcript(final_text)
    print("识别结果：", final_text)
    print(
        "识别耗时：",
        round(time.time() - start_time, 2),
        "秒",
    )
    return final_text


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

        try:
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
            return True

        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
        ):
            # Frontend 取消长轮询 /listen 时属于正常竞态，
            # 不再打印整屏 traceback。
            return False


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
                    "model": STT_MODEL_NAME,
                    "device": STT_DEVICE,
                    "compute_type": STT_COMPUTE_TYPE,
                    "engine": (
                        "sensevoice+whisper"
                        if sensevoice_model is not None
                        else "whisper"
                    ),
                    "sensevoice_state": sensevoice_state,
                    "webrtc_vad": webrtc_vad is not None,
                    "pinyin_wake": pinyin is not None,
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

            # 同一时刻只允许一个麦克风监听请求。
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

                audio, cancelled = (
                    record_one_utterance(
                        standby=standby,
                        barge_in=barge_in,
                    )
                )

                if cancelled:

                    self.send_json(
                        200,
                        {
                            "ok": True,
                            "text": "",
                            "cancelled": True,
                        },
                    )

                    return

                text = transcribe_audio(
                    audio,
                    standby=standby,
                )

                self.send_json(
                    200,
                    {
                        "ok": True,
                        "text": text,
                        "cancelled": False,
                    },
                )

            except Exception as e:

                print(
                    "语音识别失败：",
                    e
                )

                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": str(e),
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

calibrate_noise()

server = ThreadingHTTPServer(
    (HOST, PORT),
    QingyuanSTTHandler,
)

# SenseVoice 放到后台加载。这样即使首次下载模型较慢，
# /health 和 Whisper fallback 也会先可用，不会让一键启动器误判超时。
if sensevoice_state == "pending":
    threading.Thread(
        target=_load_sensevoice_background,
        daemon=True,
        name="qingyuan-sensevoice-loader",
    ).start()

print()
print("=" * 60)
print("清渊 Voice Core 2.0 / STT 服务已启动")
print(f"http://{HOST}:{PORT}")
print("监听接口：/listen")
print("打断监听：/listen?barge=1")
print("待机低偏置识别：/listen?standby=1")
print("取消接口：/cancel")
print("关闭接口：/shutdown")
print("常态监听模式已就绪（自适应双门控 VAD）")
print("=" * 60)

try:

    server.serve_forever()

except KeyboardInterrupt:

    print(
        "\n清渊语音识别服务已关闭。"
    )

finally:

    cancel_event.set()
    server.server_close()
