"""清渊 v5.3.4 时间/只读系统信息链路自检。"""

from qingyuan.router import IntentRouter
from qingyuan.system_tools import SystemTools
from qingyuan.backend_bridge import RemoteToolFactory
from qingyuan.prompts import PromptFactory


class DummyRuntime:
    pass


class DummyPermission:
    pass


def main():
    router = IntentRouter()

    samples = [
        "现在几点了",
        "今天几号",
        "今天星期几",
        "当前日期",
    ]

    for text in samples:
        intent = router.route(text)
        assert intent == "system_info", (text, intent)
        assert router.requires_tool(intent) is True
        assert router.is_action_intent(intent) is False

    assert "system_info" in RemoteToolFactory.TOOLSETS
    assert "get_current_time" in RemoteToolFactory.TOOLSETS["system_info"]

    tools = SystemTools(DummyRuntime(), DummyPermission())
    result = tools.get_current_time()
    assert "当前本机时间" in result

    prompt = PromptFactory().build("system_info")
    assert "get_current_time" in prompt
    assert "不需要 authorize_task" in prompt

    print("[OK] system_info routing")
    print("[OK] tool-required / non-action split")
    print("[OK] RemoteToolFactory exposes get_current_time")
    print("[OK] SystemTools returns local time")
    print("[OK] system_info prompt is consistent")
    print(result)


if __name__ == "__main__":
    main()
