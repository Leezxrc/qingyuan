from qingyuan.router import IntentRouter


router = IntentRouter()

tests = [
    "清渊帮我关机",
    "重启电脑",
    "让电脑睡眠",
    "锁定电脑",
    "注销当前账户",
    "打开微信",
]

for text in tests:
    print(
        text,
        "=>",
        router.route(text),
    )

print()
print(
    "本脚本只测试 Router，"
    "不会调用任何系统电源操作。"
)
