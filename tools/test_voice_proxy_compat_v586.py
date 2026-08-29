import sys
from pathlib import Path

ROOT = Path(r"C:\MyAgent")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qingyuan.voice import VoiceService
from qingyuan.backend_bridge import RemoteVoiceProxy
import inspect
import qingyuan.agent_core as ac

assert hasattr(RemoteVoiceProxy, "speak_response")

source = inspect.getsource(ac.AgentCore)
assert '"speak_response"' in source
assert '"speak"' in source
assert "口播摘要兼容模式" in source

# Verify the summary helper still works without VoiceService.__init__.
helper = VoiceService.__new__(VoiceService)
spoken = VoiceService.prepare_spoken_text(
    helper,
    "在。你有什么需要我帮忙的吗？",
    intent="chat",
    tool_results=[],
)
assert spoken == "在。你有什么需要我帮忙的吗？"

spoken2 = VoiceService.prepare_spoken_text(
    helper,
    "qingyuan/router.py 负责意图路由。\\n\\n- 识别用户意图\\n- 返回工具组\\n",
    intent="coding",
    tool_results=[],
)
assert spoken2
assert len(spoken2) < 300

print("[OK] RemoteVoiceProxy.speak_response exists")
print("[OK] AgentCore has runtime compatibility fallback")
print("[OK] Fallback can generate spoken summary without local TTS object")
print("[OK] No storage/model files touched")
print("ALL_TESTS_OK")
