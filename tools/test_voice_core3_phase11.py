import ast
from pathlib import Path

p = Path(r"C:\MyAgent\qingyuan_voice_core.py")
text = p.read_text(encoding="utf-8")
ast.parse(text)

assert "VAD_MODE = 3" in text
assert "MIN_RMS = 0.0028" in text
assert "MIN_SPEECH_MS = 260" in text
assert "MIN_VOICED_RATIO = 0.38" in text
assert "MIN_UTTERANCE_RMS = 0.0024" in text
assert "WAKE_ALIASES" in text
assert '"秦元"' in text
assert '"清约"' in text
assert "return \"清渊\" + value[len(alias):]" in text
assert "_is_noise_hallucination" in text
assert '"字幕by"' in text
assert '{"the", "a", "an", "uh", "um"}' in text
assert "弱噪声忽略" in text

print("[OK] syntax")
print("[OK] stricter WebRTC VAD mode")
print("[OK] RMS gate 0.0018 -> 0.0028")
print("[OK] minimum speech 180ms -> 260ms")
print("[OK] whole-utterance voiced-ratio/RMS gate")
print("[OK] Qingyuan wake near-homophone normalization")
print("[OK] noise/subtitle hallucination rejection")
print("ALL_TESTS_OK")
