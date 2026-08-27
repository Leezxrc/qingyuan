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
    "我的家庭群是什么",
    "我的微信家庭群叫什么",
    "家庭群是哪个",
    "现在告诉我微信群9652711是我的什么群",
    "9652711是什么群",
    "9652711对应哪个群",
]

print(
    "双向长期记忆查询测试："
)

for text in tests:
    print()
    print("Q:", text)
    print(
        "A:",
        knowledge.handle_command(
            text
        ),
    )
