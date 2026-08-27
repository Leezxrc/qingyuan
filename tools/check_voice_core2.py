import importlib.util
import json
from urllib.request import urlopen

print("Qingyuan Voice Core 2.0 dependency check")
print("=" * 58)

for module, label in {
    "webrtcvad": "WebRTC VAD",
    "pypinyin": "Pinyin wake matching",
    "modelscope": "ModelScope model loader",
    "faster_whisper": "Whisper fallback",
}.items():
    ok = importlib.util.find_spec(module) is not None
    print(f"{'[OK]' if ok else '[--]'} {label}: {module}")

try:
    import torch
    from funasr import AutoModel
    print(f"[OK] PyTorch: {torch.__version__}")
    print("[OK] SenseVoice / FunASR: AutoModel import succeeded")
except Exception as exc:
    print(f"[--] SenseVoice runtime unavailable: {type(exc).__name__}: {exc}")

print("\nSTT service health:")
try:
    with urlopen("http://127.0.0.1:8766/health", timeout=2) as r:
        data = json.loads(r.read().decode("utf-8"))
    print(json.dumps(data, ensure_ascii=False, indent=2))
except Exception as exc:
    print("STT service is not reachable:", exc)
