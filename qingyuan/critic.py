import json
import re

from ollama import chat

from .config import (
    MODEL,
    REASONING_MODEL_KEEP_ALIVE,
)


class PlanCritic:
    """
    对复杂任务计划做第二次检查。

    不能新增权限或目标，只能指出计划是否有明显问题。
    """

    def __init__(
        self,
        model_router,
    ):
        self.model_router = model_router

    @staticmethod
    def _extract_json(raw):
        text = str(raw).strip()

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.I,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def review(
        self,
        plan,
    ):
        selected_model = (
            self.model_router
            .for_planning()
        )

        prompt = f"""
你是本地电脑智能体的计划审查器。

目标：
{plan.goal}

步骤：
{plan.steps}

允许能力：
{plan.required_capabilities}

允许目标：
{plan.targets}

检查：
1. 是否漏掉关键步骤
2. 是否存在明显顺序错误
3. 是否可能造成错误目标操作
4. 是否需要在执行前增加验证
5. 绝对不能增加新的 capability 或 target

严格只返回 JSON：
{{
  "ok": true或false,
  "notes": ["短建议1","短建议2"]
}}
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
                    "num_ctx": 3072,
                    "temperature": 0,
                },
            )

            data = self._extract_json(
                response.message.content
            )

            if isinstance(data, dict):
                notes = data.get(
                    "notes",
                    [],
                )

                if isinstance(
                    notes,
                    list,
                ):
                    return [
                        str(x).strip()
                        for x in notes
                        if str(x).strip()
                    ][:5]

        except Exception:
            pass

        return []
