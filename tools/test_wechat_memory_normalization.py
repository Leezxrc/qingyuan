from qingyuan.knowledge_memory import (
    KnowledgeMemory,
)
from qingyuan.model_router import (
    ModelRouter,
)


km = KnowledgeMemory(
    ModelRouter()
)

values = [
    "微信群9652711",
    "微信群聊9652711",
    "群聊9652711",
    "微信聊天9652711",
    "9652711",
]

for value in values:
    print(
        value,
        "=>",
        km._normalize_value(
            "entity",
            "wechat_chat",
            value,
        )
    )
