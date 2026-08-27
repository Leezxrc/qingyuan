from qingyuan.knowledge_memory import (
    KnowledgeMemory,
)
from qingyuan.model_router import (
    ModelRouter,
)


knowledge = KnowledgeMemory(
    ModelRouter()
)

tests = [
    "我的微信家庭群叫什么",
    "家庭群是哪个",
    "家庭群名字是什么",
    "你还记得家庭群吗",
]

print(
    "只测试长期记忆解析；"
    "不会调用微信或桌面工具。"
)

for text in tests:
    result = (
        knowledge
        .handle_command(
            text
        )
    )

    print()
    print(
        "Q:",
        text,
    )
    print(
        "A:",
        result,
    )
