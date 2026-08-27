import re


class CognitiveRouter:
    """
    判断当前请求需要：
    - fast：快速直答
    - deep：更强模型 + 多阶段检查

    这里只决定“思考强度”，不决定权限。
    """

    DEEP_WORDS = [
        "分析",
        "规划",
        "比较",
        "为什么",
        "怎么做",
        "设计",
        "优化",
        "排查",
        "修复",
        "总结",
        "整理",
        "研究",
        "解释",
        "一步一步",
        "详细",
        "复杂",
        "帮我做",
    ]

    ACTION_INTENTS = {
        "filesystem",
        "app_launch",
        "foreground",
        "browser_search",
        "wechat_send",
        "gui",
    }

    def choose(
        self,
        text,
        intent,
    ):
        raw = str(text).strip()

        if intent in self.ACTION_INTENTS:
            return "deep"

        if len(raw) >= 80:
            return "deep"

        if any(
            word in raw
            for word in self.DEEP_WORDS
        ):
            return "deep"

        # 多条件、多步骤倾向 deep
        separators = sum(
            raw.count(x)
            for x in [
                "，",
                ",",
                "然后",
                "并且",
                "同时",
                "之后",
                "最后",
            ]
        )

        if separators >= 2:
            return "deep"

        return "fast"
