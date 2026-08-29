from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qingyuan.voice import VoiceService


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def test_short_chat_unchanged():
    voice = VoiceService.__new__(VoiceService)
    text = "雨伞的英文是 umbrella。"
    spoken = voice.prepare_spoken_text(text, intent="chat", tool_results=[])
    require(spoken == text, f"short chat was changed: {spoken!r}")


def test_coding_readonly_summary():
    voice = VoiceService.__new__(VoiceService)
    text = (
        "qingyuan/router.py 负责根据用户的输入文本判断需要加载哪个工具组。"
        "它定义了 IntentRouter 类，主要职责是：\n\n"
        "- 识别用户意图。\n"
        "- 根据意图返回对应工具组。\n\n"
        "qingyuan/factory.py 负责创建工具实例，并提供工具的注册和访问接口。"
        "它定义了 ToolFactory 类。\n\n"
        "```python\nprint('should not be spoken')\n```"
    )
    results = [
        ("code_begin_session", "CODING_SESSION_STARTED"),
        ("code_read_file", "ok"),
        ("code_finish_session", "CODING_SESSION_FINISHED"),
    ]
    spoken = voice.prepare_spoken_text(text, intent="coding", tool_results=results)
    require("router" in spoken and "factory" in spoken, spoken)
    require("qingyuan/" not in spoken, spoken)
    require("print('should not be spoken')" not in spoken, spoken)
    require("这次没有修改文件" in spoken, spoken)
    require(len(spoken) <= 220, f"spoken summary too long: {len(spoken)}")


def test_coding_write_status():
    voice = VoiceService.__new__(VoiceService)
    text = "我已经修改 qingyuan/demo.py，并完成编译检查。详细 diff 已显示。"
    results = [
        ("code_begin_session", "CODING_SESSION_STARTED"),
        ("code_write_file", "CODE_WRITE_OK"),
        ("code_run_checks", "CHECK_OK"),
        ("code_finish_session", "CODING_SESSION_FINISHED"),
    ]
    spoken = voice.prepare_spoken_text(text, intent="coding", tool_results=results)
    require("修改已经完成并通过了本轮验证" in spoken, spoken)
    require("这次没有修改文件" not in spoken, spoken)


def test_agent_core_routes_final_answer_to_spoken_summary():
    source = (ROOT / "qingyuan" / "agent_core.py").read_text(encoding="utf-8")
    require("self.voice.speak_response(" in source, "AgentCore is not using speak_response")
    require("intent=intent" in source, "AgentCore did not pass intent to spoken response")
    require("tool_results=tool_results" in source, "AgentCore did not pass tool results to spoken response")


def main():
    print("Qingyuan v5.8.2 TTS spoken-summary smoke test")
    print("=" * 58)
    test_short_chat_unchanged(); print("[OK] Short chat remains unchanged")
    test_coding_readonly_summary(); print("[OK] Coding read-only answer -> concise spoken summary")
    test_coding_write_status(); print("[OK] Coding write result -> verified spoken status")
    test_agent_core_routes_final_answer_to_spoken_summary(); print("[OK] AgentCore routes final answer through spoken-summary layer")
    print("=" * 58)
    print("ALL_TESTS_OK")
    print("No project/data files were modified by this smoke test.")


if __name__ == "__main__":
    main()
