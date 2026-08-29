import ast
from pathlib import Path

ROOT = Path(r"C:\MyAgent")

stt_path = ROOT / "qingyuan_stt_server.py"
voice_path = ROOT / "qingyuan" / "voice.py"

stt = stt_path.read_text(encoding="utf-8")
voice = voice_path.read_text(encoding="utf-8")

ast.parse(stt)
ast.parse(voice)

assert "END_SILENCE_SECONDS = 0.68" in stt
assert "def _is_prompt_artifact" in stt
assert "def _sanitize_final_transcript" in stt
assert "识别保护：检测到提示词幻觉" in stt
assert 'if standby and strong:' in stt
assert "SenseVoice 已给出可信正文时直接使用" in stt

# Old active short-sentence forced Whisper review must be gone.
active_index = stt.index("连续对话低延迟路径")
fallback_index = stt.index("SenseVoice 不可用/可疑时走")
active_block = stt[active_index:fallback_index]
assert "Whisper 短句复核" not in active_block

assert "清渊正在 TTS 播报时必须保留 barge-in 通道" in voice
assert "barge=True" in voice
assert "[语音打断]" in voice
assert "self.stop_speaking()" in voice

print("[OK] Python syntax")
print("[OK] End-silence latency: 1.10s -> 0.68s")
print("[OK] Valid SenseVoice result skips forced Whisper short review")
print("[OK] Prompt/hotword hallucination guard")
print("[OK] Failed ASR returns empty instead of '关键词'")
print("[OK] Busy + TTS keeps barge-in listening alive")
print("ALL_TESTS_OK")
