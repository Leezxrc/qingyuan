import json
import re

from ollama import chat

from .config import (
    MODEL,
    REASONING_MODEL_NUM_CTX,
    REASONING_MODEL_KEEP_ALIVE,
)


class SemanticInterpreter:
    """
    语音转录后的语义纠错层。

    目标：
    - 修正明显 ASR 同音/近音错误
    - 保留用户真正的命令、数字、路径、网址、消息正文
    - 不新增用户没说过的动作
    - 不替用户做权限决定

    默认使用主模型，但只给极短 prompt，不加载 tools。
    """

    def __init__(
        self,
        model_router,
    ):
        self.model_router = model_router

    @staticmethod
    def _extract_json(text):
        raw = str(text).strip()

        raw = re.sub(
            r"^```(?:json)?\s*",
            "",
            raw,
            flags=re.I,
        )

        raw = re.sub(
            r"\s*```$",
            "",
            raw,
        )

        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            pass

        match = re.search(
            r"\{.*\}",
            raw,
            flags=re.S,
        )

        if not match:
            return None

        try:
            data = json.loads(
                match.group(0)
            )
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @staticmethod
    def _protected_tokens(text):
        """
        这些内容不允许语义纠错器擅自改变。
        """
        raw = str(text)

        patterns = [
            # 数字 / 群号 / 日期 / 参数
            r"\d+(?:[._\-]\d+)*",

            # Windows path
            r"[A-Za-z]:\\[^\s，。！？]+",

            # URL
            r"https?://[^\s]+",

            # quoted message
            r"[“\"']([^”\"']+)[”\"']",
        ]

        tokens = []

        for pattern in patterns:
            for match in re.findall(
                pattern,
                raw,
                flags=re.I,
            ):
                if isinstance(match, tuple):
                    match = "".join(match)

                value = str(match).strip()

                if value and value not in tokens:
                    tokens.append(value)

        return tokens

    @staticmethod
    def _protected_preserved(
        original,
        corrected,
    ):
        for token in SemanticInterpreter._protected_tokens(
            original
        ):
            if token not in corrected:
                return False

        return True

    def normalize(
        self,
        text: str,
        recent_context: str = "",
    ) -> dict:
        """
        返回：
        {
          "text": "...",
          "changed": bool,
          "confidence": 0..1,
          "reason": "..."
        }
        """
        original = str(text).strip()

        if not original:
            return {
                "text": original,
                "changed": False,
                "confidence": 1.0,
                "reason": "empty",
            }

        # 太短的普通应答不调用模型，避免过度纠错。
        short_exact = {
            "是",
            "否",
            "同意",
            "确认",
            "取消",
            "可以",
            "好的",
            "好",
            "在吗",
            "你好",
        }

        if original.strip("。！？!?，, ") in short_exact:
            return {
                "text": original,
                "changed": False,
                "confidence": 1.0,
                "reason": "short_exact",
            }

        protected = self._protected_tokens(
            original
        )

        prompt = f"""
你是中文语音识别后的语义纠错器。

任务：
判断“原始转录”里是否存在明显的同音字、近音词、ASR 错字。
只修正语言识别错误，不改变用户真正的意图。

强制规则：
1. 不新增任何用户没要求的动作。
2. 数字、群号、日期、文件路径、网址必须原样保留。
3. 用户要发送的消息正文必须原样保留。
4. 只在语境非常明确时纠错。
5. 不确定时保持原文。
6. 电脑操作常见词包括：
   浏览器、Chrome、微信、微信群聊、搜索、发送、打开、
   前台、文件、文件夹、桌面、下载、明日方舟、清渊。
7. 例如：
   “微信群条9652711中发送你好”
   应理解为“微信群聊9652711中发送你好”。
8. 不要解释，只返回 JSON。

最近上下文：
{recent_context[:500]}

原始转录：
{original}

受保护内容：
{protected}

严格输出：
{{
  "corrected_text": "纠正后的完整句子",
  "changed": true或false,
  "confidence": 0到1,
  "reason": "一句很短的原因"
}}
""".strip()

        try:
            selected_model = (
                self.model_router
                .for_semantic_interpretation()
            )

            response = chat(
                model=selected_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                think=False,
                stream=False,
                keep_alive=(
                    REASONING_MODEL_KEEP_ALIVE
                    if selected_model != MODEL
                    else "2m"
                ),
                options={
                    "num_ctx": min(
                        REASONING_MODEL_NUM_CTX,
                        4096,
                    ),
                    "temperature": 0,
                },
            )

            raw = response.message.content

        except Exception as e:
            return {
                "text": original,
                "changed": False,
                "confidence": 0.0,
                "reason": f"interpreter_error:{e}",
            }

        data = self._extract_json(raw)

        if not data:
            return {
                "text": original,
                "changed": False,
                "confidence": 0.0,
                "reason": "invalid_json",
            }

        corrected = str(
            data.get(
                "corrected_text",
                original,
            )
        ).strip()

        try:
            confidence = float(
                data.get(
                    "confidence",
                    0,
                )
            )
        except Exception:
            confidence = 0.0

        changed = bool(
            data.get(
                "changed",
                corrected != original,
            )
        )

        # 受保护 token 被改了，直接否决语义纠错。
        if not self._protected_preserved(
            original,
            corrected,
        ):
            return {
                "text": original,
                "changed": False,
                "confidence": 0.0,
                "reason": "protected_token_changed",
            }

        # 低置信度也不改。
        if (
            not changed
            or confidence < 0.82
            or not corrected
        ):
            return {
                "text": original,
                "changed": False,
                "confidence": confidence,
                "reason": str(
                    data.get(
                        "reason",
                        "unchanged",
                    )
                ),
            }

        return {
            "text": corrected,
            "changed": True,
            "confidence": confidence,
            "reason": str(
                data.get(
                    "reason",
                    "semantic_correction",
                )
            ),
        }
