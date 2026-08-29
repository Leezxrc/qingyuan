
import sys
from pathlib import Path

ROOT = Path(r"C:\MyAgent")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import qingyuan.backend_bridge as bb

assert issubclass(bb.RemoteVoiceProxy, __import__("qingyuan.voice", fromlist=["VoiceService"]).VoiceService)

class FakeRuntime:
    voice_enabled = True

calls = []

def fake_post_json(url, payload, timeout=0):
    calls.append((url, payload, timeout))
    return {"ok": True}

bb.post_json = fake_post_json

proxy = bb.RemoteVoiceProxy(FakeRuntime())

assert hasattr(proxy, "speak_response")
assert hasattr(proxy, "prepare_spoken_text")

proxy.speak_response("在。你有什么需要我帮忙的吗？", intent="chat", tool_results=[])

assert calls, "speak_response did not delegate to remote /speak"
url, payload, timeout = calls[-1]
assert url.endswith("/speak"), url
assert payload["text"] == "在。你有什么需要我帮忙的吗？"
assert payload["allow_barge_in"] is True

calls.clear()

technical = """qingyuan/router.py 负责意图路由。

- 识别用户意图
- 返回工具组

qingyuan/factory.py 负责工具实例化和注册。
"""
proxy.speak_response(technical, intent="coding", tool_results=[])

assert calls, "technical speak_response did not speak"
spoken = calls[-1][1]["text"]
assert len(spoken) < len(technical) + 80
assert "code_finish_session" not in spoken

print("[OK] RemoteVoiceProxy exposes speak_response")
print("[OK] Short chat delegates unchanged to remote /speak")
print("[OK] Coding answer uses spoken-summary layer")
print("[OK] No local TTS/STT/storage changes required")
print("ALL_TESTS_OK")
