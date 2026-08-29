from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qingyuan.voice import VoiceService


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class RuntimeStub:
    def __init__(self):
        self.echo_lock = threading.Lock()
        self.last_tts_text = ""
        self.last_tts_end_time = 0.0
        self.tts_speaking = threading.Event()
        self.activity = []
        self.active = True
        self.voice_enabled = True
    def is_conversation_active(self):
        return self.active
    def mark_activity(self, source="activity"):
        self.activity.append(source)


def test_live_and_tail_echo_filter():
    rt = RuntimeStub()
    voice = VoiceService(rt)
    rt.last_tts_text = "我已经检查完了，详细结果已经显示在屏幕上。"
    rt.tts_speaking.set()
    require(voice._looks_like_recent_tts_echo("详细结果已经显示在屏幕上"), "live TTS echo was not filtered")
    rt.tts_speaking.clear()
    rt.last_tts_end_time = time.monotonic()
    require(voice._looks_like_recent_tts_echo("结果已经显示在屏幕上"), "tail TTS echo was not filtered")


def test_normal_followup_not_overfiltered():
    rt = RuntimeStub()
    voice = VoiceService(rt)
    rt.last_tts_text = "雨伞的英文是 umbrella。"
    rt.last_tts_end_time = time.monotonic()
    require(not voice._looks_like_recent_tts_echo("那雨衣呢"), "normal follow-up was over-filtered")


def test_continuous_conversation_refresh_present():
    source = (ROOT / "qingyuan" / "voice.py").read_text(encoding="utf-8")
    require('mark_activity("tts_start")' in source, "TTS start does not refresh active conversation")
    require('mark_activity("tts_end")' in source, "TTS end does not refresh active conversation")
    require('0 <= since_tts < 0.22' in source, "post-TTS tail cooldown missing")


def test_barge_gate_configuration():
    source = (ROOT / "qingyuan_stt_server.py").read_text(encoding="utf-8")
    require('"0.009"' in source, "barge RMS floor not rebalanced")
    require('BARGE_CONFIRM_SECONDS = 0.28' in source, "barge confirmation window missing")
    require('BARGE_START_RATIO = 0.78' in source, "barge voice ratio missing")
    require('"打断实际能量门槛："' in source, "barge threshold diagnostic missing")


def main():
    print("Qingyuan v5.8.3 voice stability smoke test")
    print("=" * 58)
    test_live_and_tail_echo_filter(); print("[OK] Live/TTS-tail self-echo filter")
    test_normal_followup_not_overfiltered(); print("[OK] Normal follow-up is not over-filtered")
    test_continuous_conversation_refresh_present(); print("[OK] Continuous conversation window refresh + tail cooldown")
    test_barge_gate_configuration(); print("[OK] Barge-in VAD gate rebalance")
    print("=" * 58)
    print("ALL_TESTS_OK")
    print("No project/data files were modified by this smoke test.")


if __name__ == "__main__":
    main()
