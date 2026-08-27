import json
from pathlib import Path

from ollama import chat

from .config import (
    MODEL,
    REASONING_MODEL_KEEP_ALIVE,
)


SUMMARY_FILE = Path(
    r"C:\MyAgent\data\conversation_summary.json"
)


class ConversationContextManager:
    """
    长对话上下文管理。

    不再只依赖最近 4 条：
    - 最近消息继续保留
    - 更早内容压缩成滚动摘要
    """

    def __init__(
        self,
        model_router,
    ):
        self.model_router = model_router
        self.summary = ""
        self._load()

    def _load(self):
        try:
            if SUMMARY_FILE.exists():
                data = json.loads(
                    SUMMARY_FILE.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(data, dict):
                    self.summary = str(
                        data.get(
                            "summary",
                            "",
                        )
                    ).strip()
        except Exception:
            self.summary = ""

    def _save(self):
        SUMMARY_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        SUMMARY_FILE.write_text(
            json.dumps(
                {
                    "summary": self.summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def maybe_update(
        self,
        messages,
        keep_recent=6,
    ):
        """
        消息较多时，把较旧部分压缩。
        """
        if len(messages) <= 12:
            return

        older = messages[:-keep_recent]

        chunks = []

        for item in older[-12:]:
            if not isinstance(item, dict):
                continue

            role = str(
                item.get(
                    "role",
                    "",
                )
            )

            content = str(
                item.get(
                    "content",
                    "",
                )
            ).strip()

            if content:
                chunks.append(
                    f"{role}: {content[:500]}"
                )

        if not chunks:
            return

        selected_model = (
            self.model_router
            .for_semantic_interpretation()
        )

        prompt = f"""
你是本地智能体的对话摘要器。

已有摘要：
{self.summary[:2000]}

需要合并的新旧对话：
{chr(10).join(chunks)}

只保留以后可能真正有用的信息：
- 用户明确目标
- 已确认的决定
- 重要上下文
- 未完成任务
- 软件/项目状态
- 关系与定义

不要保留闲聊废话。
不要添加对话中没有的信息。

输出一段紧凑中文摘要。
""".strip()

        try:
            response = chat(
                model=selected_model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                }],
                think=False,
                stream=False,
                keep_alive=REASONING_MODEL_KEEP_ALIVE,
                options={
                    "num_ctx": 4096,
                    "temperature": 0,
                },
            )

            new_summary = (
                response.message.content
                .strip()
            )

            if new_summary:
                self.summary = (
                    new_summary[:5000]
                )

                self._save()

        except Exception:
            pass

    def context_text(self):
        if not self.summary:
            return "目前没有历史对话摘要。"

        return self.summary
