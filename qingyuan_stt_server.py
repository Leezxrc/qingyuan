import json
import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from urllib.parse import urlparse, parse_qs

import numpy as np
import sounddevice as sd

from faster_whisper import WhisperModel


# ============================================================
# 配置
# ============================================================

HOST = "127.0.0.1"
PORT = 8766

SAMPLE_RATE = 16000
CHANNELS = 1

MIC_DEVICE = 1

BLOCK_DURATION = 0.05
BLOCK_SIZE = int(
    SAMPLE_RATE * BLOCK_DURATION
)

PRE_ROLL_SECONDS = 0.55
END_SILENCE_SECONDS = 2.00
MAX_RECORD_SECONDS = 30

CALIBRATION_SECONDS = 1.0

# 防止键盘敲击等极短声音误触发。
START_CONFIRM_SECONDS = 0.10

# 连续对话中，清渊正在说话时用于强制打断。
# 因为音箱声音也可能漏进麦克风，所以打断阈值比普通监听高。
BARGE_CONFIRM_SECONDS = 0.15
BARGE_MIN_THRESHOLD = 0.025
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


# ============================================================
# Whisper
# ============================================================

print("=" * 60)
print("正在加载清渊语音识别系统……")

model = WhisperModel(
    STT_MODEL_NAME,
    device=STT_DEVICE,
    compute_type=STT_COMPUTE_TYPE,
)

print(
    "STT 模型：",
    STT_MODEL_NAME,
    "| device:",
    STT_DEVICE,
    "| compute:",
    STT_COMPUTE_TYPE,
)
print("清渊语音识别模型加载完成")
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
        noise_rms * 3.0,
        0.008,
    )

    print(
        "环境底噪：",
        round(noise_rms, 5)
    )

    print(
        "语音触发阈值：",
        round(speech_threshold, 5)
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
    barge_in: bool = False
):

    cancel_event.clear()

    pre_roll_blocks = max(
        1,
        int(
            PRE_ROLL_SECONDS
            / BLOCK_DURATION
        )
    )

    confirm_seconds = (
        BARGE_CONFIRM_SECONDS
        if barge_in
        else START_CONFIRM_SECONDS
    )

    confirm_blocks = max(
        1,
        int(
            confirm_seconds
            / BLOCK_DURATION
        )
    )

    active_threshold = (
        max(
            speech_threshold
            * BARGE_THRESHOLD_MULTIPLIER,
            BARGE_MIN_THRESHOLD,
        )
        if barge_in
        else speech_threshold
    )

    pre_buffer = deque(
        maxlen=pre_roll_blocks
    )

    recorded_blocks = []

    speech_started = False
    above_threshold_blocks = 0

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

            block, _ = stream.read(
                BLOCK_SIZE
            )

            audio = (
                block[:, 0]
                .copy()
            )

            rms = calculate_rms(
                audio
            )

            if not speech_started:

                pre_buffer.append(
                    audio
                )

                if rms >= active_threshold:

                    above_threshold_blocks += 1

                else:

                    above_threshold_blocks = 0

                if (
                    above_threshold_blocks
                    >= confirm_blocks
                ):

                    speech_started = True

                    now = time.time()

                    speech_start_time = now
                    last_voice_time = now

                    recorded_blocks.extend(
                        list(pre_buffer)
                    )

                    print(
                        "🟢 检测到说话"
                    )

                    if barge_in:

                        print(
                            "⏹ 检测到用户打断，停止清渊当前播报"
                        )

                        stop_tts_playback()

            else:

                recorded_blocks.append(
                    audio
                )

                if rms >= active_threshold:

                    last_voice_time = (
                        time.time()
                    )

                if cancel_event.is_set():
                    return None, True

                silence_duration = (
                    time.time()
                    - last_voice_time
                )

                if (
                    silence_duration
                    >= END_SILENCE_SECONDS
                ):

                    print(
                        "🔴 检测到停顿"
                    )

                    break

                total_duration = (
                    time.time()
                    - speech_start_time
                )

                if (
                    total_duration
                    >= MAX_RECORD_SECONDS
                ):

                    print(
                        "🔴 达到最长录音时间"
                    )

                    break

    if not recorded_blocks:
        return None, False

    audio_data = np.concatenate(
        recorded_blocks
    )

    print(
        "录音时长：",
        round(
            len(audio_data)
            / SAMPLE_RATE,
            2
        ),
        "秒"
    )

    return audio_data, False


# ============================================================
# Whisper 转录
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


def _contains_wake_pattern(
    text: str
) -> bool:

    normalized = text.strip()

    if "清渊" in normalized:
        return True

    for index in range(
        len(normalized) - 1
    ):

        first = normalized[index]
        second = normalized[index + 1]

        if (
            first in WAKE_FIRST_CHARS
            and second in WAKE_SECOND_CHARS
        ):

            return True

    return False


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
    # 待机状态：
    # 第一遍不使用强 hotwords，只在 prompt 中轻提示“清渊”可能存在。
    # 这样降低误唤醒，同时配合更长 pre-roll 减少句首被吞。
    # --------------------------------------------------------

    if standby:
        first_text, first_metrics = (
            _transcribe_candidate(
                audio_data,
                standby=True,
                strong=False,
                use_hotwords=False,
            )
        )

        if cancel_event.is_set():
            return ""

        print(
            "待机第一遍识别：",
            first_text
        )

        if not _contains_wake_pattern(
            first_text
        ):
            print(
                "待机判定：未检测到‘清渊’近音"
            )

            print(
                "识别耗时：",
                round(
                    time.time()
                    - start_time,
                    2
                ),
                "秒"
            )

            return first_text

        # 第二遍使用动态 hotwords + 更大 beam 做严格确认。
        second_text, second_metrics = (
            _transcribe_candidate(
                audio_data,
                standby=True,
                strong=True,
                use_hotwords=True,
            )
        )

        if cancel_event.is_set():
            return ""

        print(
            "待机第二遍确认：",
            second_text
        )

        if not _contains_wake_pattern(
            second_text
        ):
            print(
                "待机判定：唤醒确认失败"
            )

            print(
                "识别耗时：",
                round(
                    time.time()
                    - start_time,
                    2
                ),
                "秒"
            )

            # 真正双确认：第二遍没有确认到唤醒词时返回空，
            # 避免第一遍的误识别继续把 Agent 唤醒。
            return ""

        final_text = second_text
        _remember_transcript(final_text)

        print(
            "待机判定：‘清渊’近音确认通过"
        )

        print(
            "识别结果：",
            final_text
        )

        print(
            "识别耗时：",
            round(
                time.time()
                - start_time,
                2
            ),
            "秒"
        )

        return final_text

    # --------------------------------------------------------
    # 已唤醒 / 连续对话：
    # 第一遍使用动态 hotwords。
    # 只有低置信度时才自动进行第二遍强解码，避免每句话都变慢。
    # --------------------------------------------------------

    first_text, first_metrics = (
        _transcribe_candidate(
            audio_data,
            standby=False,
            strong=False,
            use_hotwords=True,
        )
    )

    final_text = first_text

    if _needs_retry(
        first_text,
        first_metrics,
    ):
        print(
            "识别置信度不足，正在自动二次识别……"
        )

        second_text, second_metrics = (
            _transcribe_candidate(
                audio_data,
                standby=False,
                strong=True,
                use_hotwords=True,
            )
        )

        final_text = _choose_better_candidate(
            first_text,
            first_metrics,
            second_text,
            second_metrics,
        )

    final_text = apply_transcript_corrections(
        final_text
    )

    if cancel_event.is_set():
        return ""

    _remember_transcript(final_text)

    print(
        "识别结果：",
        final_text
    )

    print(
        "识别耗时：",
        round(
            time.time()
            - start_time,
            2
        ),
        "秒"
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
                    "model": STT_MODEL_NAME,
                    "device": STT_DEVICE,
                    "compute_type": STT_COMPUTE_TYPE,
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
                        barge_in=barge_in
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

print()
print("=" * 60)
print("清渊语音识别服务已启动")
print(f"http://{HOST}:{PORT}")
print("监听接口：/listen")
print("打断监听：/listen?barge=1")
print("待机低偏置识别：/listen?standby=1")
print("取消接口：/cancel")
print("关闭接口：/shutdown")
print("常态监听模式已就绪")
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
