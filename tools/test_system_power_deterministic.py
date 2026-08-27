from qingyuan.backend_service import (
    BrainBackend,
)


tests = {
    "清渊帮我关机": "shutdown",
    "把电脑关掉": "shutdown",
    "重启电脑": "restart",
    "让电脑进入睡眠": "sleep",
    "锁定电脑": "lock",
    "注销当前账户": "logout",
    "打开微信": None,
}

for text, expected in tests.items():
    actual = (
        BrainBackend
        ._resolve_system_power_action(
            text
        )
    )

    print(
        text,
        "=>",
        actual,
        "| expected:",
        expected,
    )

    assert actual == expected

print()
print(
    "通过。这个测试只检查动作解析，"
    "不会执行关机/重启/锁屏等操作。"
)
