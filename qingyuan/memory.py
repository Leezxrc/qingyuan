import json

from .config import MEMORY_FILE, DATA_DIR


class MemoryStore:
    def __init__(
        self,
        runtime,
        voice,
        knowledge=None,
    ):
        self.runtime = runtime
        self.voice = voice
        self.knowledge = knowledge
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not MEMORY_FILE.exists():
            MEMORY_FILE.write_text("[]", encoding="utf-8")

    def load(self):
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save(self, memories):
        MEMORY_FILE.write_text(
            json.dumps(memories, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def memory_context(self):
        items = self.load()

        legacy = (
            "\n".join(
                f"- {x}"
                for x in items
            )
            if items
            else "无旧版自由文本记忆。"
        )

        if self.knowledge is None:
            return legacy

        return (
            "【自由文本记忆】\n"
            + legacy
            + "\n\n【结构化长期知识】\n"
            + self.knowledge.context_text()
        )

    def relevant_memory_context(
        self,
        query,
    ):
        if self.knowledge is None:
            return self.memory_context()

        return (
            "【与当前问题相关的长期知识】\\n"
            + self.knowledge.relevant_context(
                query
            )
        )

    def remember_memory(self, content: str) -> str:
        """保存用户明确要求记住的一条长期记忆。"""
        content = str(content).strip()
        if not content:
            return "没有提供需要记住的内容。"

        forbidden = [
            "password", "密码", "api key", "apikey",
            "银行卡", "信用卡", "私钥", "token", "身份证",
        ]
        if any(x in content.lower() for x in forbidden):
            return "拒绝保存：该内容可能包含不适合明文长期保存的敏感信息。"

        if not self.voice.request_confirmation(
            f"长期记忆：{content}\n允许保存吗？",
            operation_name="保存长期记忆",
        ):
            return "用户拒绝保存这条长期记忆。"

        memories = self.load()
        if content not in memories:
            memories.append(content)
            self.save(memories)
        self.runtime.mark_activity("remember_memory")
        return "长期记忆保存成功。"

    def list_memories(self) -> str:
        """列出当前长期记忆。"""
        memories = self.load()
        if not memories:
            return "目前没有保存任何长期记忆。"
        return "\n".join(
            f"{i}. {m}" for i, m in enumerate(memories, 1)
        )

    def forget_memory(self, keyword: str) -> str:
        """删除包含指定关键词的长期记忆。"""
        keyword = str(keyword).strip()
        memories = self.load()
        matches = [m for m in memories if keyword.lower() in m.lower()]
        if not matches:
            return f"没有找到包含“{keyword}”的长期记忆。"

        if not self.voice.request_confirmation(
            "将删除：\n" + "\n".join(f"- {m}" for m in matches),
            operation_name="删除长期记忆",
        ):
            return "用户拒绝删除长期记忆。"

        self.save([m for m in memories if m not in matches])
        self.runtime.mark_activity("forget_memory")
        return f"已删除 {len(matches)} 条长期记忆。"
