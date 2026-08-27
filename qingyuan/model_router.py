import threading

from ollama import list as ollama_list

from .config import (
    MODEL,
    REASONING_MODEL,
)


class ModelRouter:
    """
    双模型路由：

    - chat / 简单记忆问答 -> 4B
    - 复杂电脑任务 / 规划 / 语义纠错 -> 强模型

    强模型不可用时自动回退 4B。
    """

    COMPLEX_INTENTS = {
        "filesystem",
        "app_launch",
        "foreground",
        "browser_search",
        "wechat_send",
        "gui",
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._reasoning_available = None

    def refresh(self):
        with self._lock:
            self._reasoning_available = (
                self._check_reasoning_model()
            )
        return self._reasoning_available

    def _check_reasoning_model(self):
        try:
            response = ollama_list()

            models = getattr(
                response,
                "models",
                [],
            )

            names = []

            for item in models:
                name = getattr(
                    item,
                    "model",
                    None,
                )

                if not name:
                    name = getattr(
                        item,
                        "name",
                        None,
                    )

                if name:
                    names.append(
                        str(name)
                    )

            target = (
                REASONING_MODEL
                .split(":")[0]
                .lower()
            )

            full = REASONING_MODEL.lower()

            for name in names:
                lower = name.lower()

                if (
                    lower == full
                    or lower.startswith(
                        full + ":"
                    )
                    or (
                        target in lower
                        and "8b" in lower
                        and "qwen3" in lower
                    )
                ):
                    return True

        except Exception:
            pass

        return False

    def reasoning_available(self):
        with self._lock:
            cached = self._reasoning_available

        if cached is None:
            return self.refresh()

        return cached

    def for_intent(self, intent):
        if (
            intent in self.COMPLEX_INTENTS
            and self.reasoning_available()
        ):
            return REASONING_MODEL

        return MODEL

    def for_semantic_interpretation(self):
        if self.reasoning_available():
            return REASONING_MODEL

        return MODEL

    def for_planning(self):
        if self.reasoning_available():
            return REASONING_MODEL

        return MODEL

    def status_text(self):
        if self.reasoning_available():
            return (
                f"聊天：{MODEL}；"
                f"复杂任务：{REASONING_MODEL}"
            )

        return (
            f"聊天：{MODEL}；"
            f"复杂任务：{MODEL}（强模型未安装，已回退）"
        )
