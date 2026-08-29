from __future__ import annotations

import sys
import tempfile
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Planner/AgentCore only need the symbol to exist; smoke test never calls a model.
try:
    import ollama  # noqa: F401
except ModuleNotFoundError:
    fake_ollama = types.ModuleType("ollama")
    def _no_model_call(*args, **kwargs):
        raise RuntimeError("Smoke test must not call Ollama")
    fake_ollama.chat = _no_model_call
    sys.modules["ollama"] = fake_ollama

from qingyuan.router import IntentRouter
from qingyuan.system_tools import SystemTools
from qingyuan.planner import Planner
from qingyuan.config import MODEL

# The hotfix ZIP intentionally does not overwrite wake.py; the real installation already has it.
# Provide the single symbol voice.py imports so this isolated ZIP smoke test can run.
if "qingyuan.wake" not in sys.modules:
    fake_wake = types.ModuleType("qingyuan.wake")
    fake_wake.strip_wake_word = lambda text: (False, str(text))
    sys.modules["qingyuan.wake"] = fake_wake

from qingyuan.voice import VoiceService
from qingyuan.agent_core import AgentCore


class FakeRuntime:
    def __init__(self):
        self.actions = []
        self.echo_lock = threading.Lock()
        self.last_tts_text = ""
        self.last_tts_end_time = 0.0
        self.tts_speaking = threading.Event()
        self.voice_enabled = True

    def record_desktop_action(self, action):
        self.actions.append(str(action))


class FakePermission:
    def __init__(self, request, allowed=None):
        self._request = str(request)
        self.allowed = set(allowed or {"file_read", "file_write", "code_execute"})
        self.ended = False

    def original_request(self):
        return self._request

    def require(self, capability, target=None):
        if capability in self.allowed:
            return True, ""
        return False, f"capability not granted in smoke test: {capability}"

    def has(self, capability):
        return capability in self.allowed

    def end_task(self):
        self.ended = True
        return "TEST_PERMIT_ENDED"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class FakeModelRouter:
    def for_planning(self):
        return MODEL


def test_router():
    router = IntentRouter()
    require(router.route("清渊，给自己增加一个代码功能") == "coding", "self-development did not route to coding")
    require(router.route("清渊，检查你自己的代码，只检查不要修改") == "coding", "read-only self code inspection did not route to coding")
    require(router.route("帮我写一段 Python 代码示例") == "chat", "plain code-generation should remain chat")


def test_planner_least_privilege():
    planner = Planner(FakeModelRouter())
    read_plan = planner.create("coding", r"清渊，检查你自己的代码，只检查 C:\MyAgent\qingyuan\router.py，不要修改。")
    require(read_plan.targets == [r"C:\MyAgent"], f"unexpected target: {read_plan.targets}")
    require(read_plan.required_capabilities == ["file_read"], f"read-only over-permission: {read_plan.required_capabilities}")

    write_plan = planner.create("coding", "清渊，给自己增加一个测试功能并运行编译检查")
    require(write_plan.required_capabilities == ["file_read", "file_write", "code_execute"], f"unexpected write caps: {write_plan.required_capabilities}")


def test_readonly_session_without_code_execute():
    with tempfile.TemporaryDirectory(prefix="qingyuan_v581_ro_") as td:
        root = Path(td).resolve()
        demo = root / "demo.py"
        demo.write_text("value = 1\n", encoding="utf-8")
        permission = FakePermission(f"只检查项目代码 {root} 不要修改", allowed={"file_read"})
        runtime = FakeRuntime()
        tools = SystemTools(runtime, permission)

        result = tools.code_begin_session(str(root))
        require("CODING_SESSION_STARTED" in result, result)
        require("跳过 Git 基线" in result, result)
        result = tools.code_read_file("demo.py")
        require("value = 1" in result, result)
        result = tools.code_finish_session()
        require("CODING_SESSION_FINISHED" in result, result)
        require(permission.ended, "read-only permit was not revoked")


def test_session_write_check_finish():
    with tempfile.TemporaryDirectory(prefix="qingyuan_v581_") as td:
        root = Path(td).resolve()
        demo = root / "demo.py"
        demo.write_text("value = 1\n", encoding="utf-8")
        permission = FakePermission(f"请修改项目代码 {root}")
        runtime = FakeRuntime()
        tools = SystemTools(runtime, permission)
        require("CODING_SESSION_STARTED" in tools.code_begin_session(str(root)), "session did not start")
        require("CODE_WRITE_OK" in tools.code_write_file("demo.py", "value = 2\n"), "write failed")
        require("CODING_SESSION_NOT_VERIFIED" in tools.code_finish_session(), "unverified write falsely finished")
        require("CHECK_OK" in tools.code_run_checks("compile", "demo.py"), "compile failed")
        require("CODING_SESSION_FINISHED" in tools.code_finish_session(), "verified session did not finish")
        require(permission.ended, "permit not revoked")


def test_auto_finish_helper():
    class Plan:
        verify_mode = "coding_result"

    fake_agent = AgentCore.__new__(AgentCore)
    fake_agent.messages = []
    calls = []
    def finish():
        calls.append(1)
        return "CODING_SESSION_FINISHED\nTEST"

    results = [("code_begin_session", "CODING_SESSION_STARTED"), ("code_read_file", "ok")]
    out = AgentCore._auto_finish_coding_session(fake_agent, Plan(), results, {"code_finish_session": finish})
    require("CODING_SESSION_FINISHED" in out, out)
    require(len(calls) == 1, "auto finish was not called exactly once")
    require(results[-1][0] == "code_finish_session", "auto finish result not recorded")


def test_echo_partial_filter():
    runtime = FakeRuntime()
    voice = VoiceService(runtime)
    runtime.last_tts_text = "任务没有完成：Coding Session 尚未调用 code_finish_session 完成验证。"
    runtime.last_tts_end_time = time.monotonic() - 0.5
    require(voice._looks_like_recent_tts_echo("尚未调用coded finish"), "partial ASR echo was not filtered")

    runtime.last_tts_text = "今天天气不错。"
    runtime.last_tts_end_time = time.monotonic() - 0.5
    require(not voice._looks_like_recent_tts_echo("帮我打开网易云音乐"), "unrelated user command was falsely filtered")


def test_exact_rollback():
    with tempfile.TemporaryDirectory(prefix="qingyuan_v581_rb_") as td:
        root = Path(td).resolve()
        demo = root / "demo.py"
        original = b"answer = 41\n"
        demo.write_bytes(original)
        permission = FakePermission(f"修复项目代码 {root}")
        runtime = FakeRuntime()
        tools = SystemTools(runtime, permission)
        require("CODING_SESSION_STARTED" in tools.code_begin_session(str(root)), "rollback session did not start")
        require("CODE_WRITE_OK" in tools.code_write_file("demo.py", "answer = 42\n"), "rollback edit failed")
        require("CODE_ROLLBACK_OK" in tools.code_rollback(), "rollback failed")
        require(demo.read_bytes() == original, "rollback did not restore bytes")


def main():
    print("Qingyuan v5.8.1 hotfix smoke test")
    print("=" * 58)
    test_router(); print("[OK] Router")
    test_planner_least_privilege(); print("[OK] Read-only least privilege")
    test_readonly_session_without_code_execute(); print("[OK] Read-only session: file_read only -> finish")
    test_session_write_check_finish(); print("[OK] Write session verification gate")
    test_auto_finish_helper(); print("[OK] Coding Session auto-finish mechanical close")
    test_echo_partial_filter(); print("[OK] Partial TTS self-echo filter")
    test_exact_rollback(); print("[OK] Session-local rollback")
    print("=" * 58)
    print("ALL_TESTS_OK")
    print("Temporary directories only; C:\\MyAgent project/data were not modified.")


if __name__ == "__main__":
    main()
