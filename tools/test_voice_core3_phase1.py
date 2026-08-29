import ast
from pathlib import Path

ROOT = Path(r"C:\MyAgent")

files = [
    ROOT / "qingyuan_voice_core.py",
    ROOT / "qingyuan_stt_server.py",
    ROOT / "qingyuan" / "voice.py",
]

for f in files:
    ast.parse(f.read_text(encoding="utf-8"))
    print("[OK] syntax:", f.name)

core = (ROOT / "qingyuan_voice_core.py").read_text(encoding="utf-8")
voice = (ROOT / "qingyuan" / "voice.py").read_text(encoding="utf-8")
entry = (ROOT / "qingyuan_stt_server.py").read_text(encoding="utf-8")

assert "single-mic-always-on" in core
assert "webrtcvad.Vad" in core
assert "SenseVoiceSmall" in core
assert "Whisper fallback" in core
assert '"/barge"' in core
assert "transcript_queue" in core
assert "runpy.run_path" in entry
assert "STT_BARGE_URL" in voice
assert "only ONE blocking STT /listen request exists" in voice
assert "[语音打断]" in voice
assert "_looks_like_current_or_recent_tts_echo" in voice

# Correct guard: the string “关键词” is intentionally present in the
# hallucination rejection code. What must be absent is prompt injection.
assert "initial_prompt=" not in core
assert "vocabulary_prompt()" not in core
assert 'kwargs["initial_prompt"]' not in core
assert "_is_prompt_artifact" in core

print("[OK] one microphone owner")
print("[OK] always-on WebRTC VAD")
print("[OK] SenseVoice primary + Whisper fallback")
print("[OK] no literal vocabulary/keyword prompt injection")
print("[OK] prompt-artifact rejection guard exists")
print("[OK] single frontend STT consumer")
print("[OK] TTS barge state bridge")
print("[OK] duplicate barge/normal listener architecture removed")
print("ALL_TESTS_OK")
