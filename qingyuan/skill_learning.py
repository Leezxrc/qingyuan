import json
import re
import time
from pathlib import Path

from ollama import chat

from .config import (
    REASONING_MODEL_KEEP_ALIVE,
)


CANDIDATE_DIR = Path(
    r"C:\MyAgent\skills\candidates"
)

LEARNED_DIR = Path(
    r"C:\MyAgent\skills\learned"
)

LEARNING_STATE = Path(
    r"C:\MyAgent\data\skill_learning_state.json"
)


class SkillLearningManager:
    """
    从成功任务中提炼“候选技能”。

    重要：
    - 只学习流程，不学习权限。
    - 不修改 Task Permit。
    - 不把一次成功直接当成永久技能。
    - 候选技能达到最小成功次数后，才自动晋升 learned。
    """

    def __init__(
        self,
        model_router,
        min_successes=2,
    ):
        self.model_router = model_router
        self.min_successes = max(
            2,
            int(min_successes),
        )

        CANDIDATE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        LEARNED_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        LEARNING_STATE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not LEARNING_STATE.exists():
            LEARNING_STATE.write_text(
                json.dumps(
                    {
                        "fingerprints": {},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    @staticmethod
    def _safe_name(value):
        value = str(value).strip().lower()

        value = re.sub(
            r"[^a-z0-9_\-\u4e00-\u9fff]+",
            "_",
            value,
        ).strip("_")

        return (
            value[:60]
            or "skill"
        )

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
            data = json.loads(
                text
            )

            return (
                data
                if isinstance(
                    data,
                    dict,
                )
                else None
            )

        except Exception:
            pass

        match = re.search(
            r"\{.*\}",
            text,
            flags=re.S,
        )

        if not match:
            return None

        try:
            data = json.loads(
                match.group(0)
            )

            return (
                data
                if isinstance(
                    data,
                    dict,
                )
                else None
            )

        except Exception:
            return None

    @staticmethod
    def _load_state():
        try:
            data = json.loads(
                LEARNING_STATE.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(data, dict):
                return data

        except Exception:
            pass

        return {
            "fingerprints": {},
        }

    @staticmethod
    def _save_state(data):
        LEARNING_STATE.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _derive_skill(
        self,
        *,
        intent,
        user_goal,
        plan_steps,
        tool_results,
        verifier_result,
    ):
        selected_model = (
            self.model_router
            .for_planning()
        )

        prompt = f"""
你是本地智能体的技能学习器。

下面是一项已经成功完成的真实任务。

intent:
{intent}

用户目标:
{user_goal}

计划步骤:
{plan_steps}

真实工具结果:
{tool_results}

最终验证:
{verifier_result}

请把它提炼成“可复用流程”，而不是把一次任务的具体内容原样保存。

要求：
1. 不保存用户的具体消息正文。
2. 不保存一次性的群号、文件名、搜索词等参数值。
3. 使用参数占位符，例如：
   <chat_target>
   <message>
   <query>
   <path>
4. 只保留稳定的操作步骤。
5. required_capabilities 只能来自原任务已经使用过的权限。
6. 绝对不能写“自动授权”“跳过确认”等内容。
7. 如果这个任务不值得复用，learn=false。
8. 不要学习普通闲聊。
9. 不要学习失败任务。

严格只返回 JSON：
{{
  "learn": true,
  "skill_key": "稳定英文短名",
  "name": "中文技能名",
  "description": "一句话说明",
  "triggers": ["触发短语1","触发短语2"],
  "parameters": ["<param1>","<param2>"],
  "steps": ["步骤1","步骤2"],
  "required_capabilities": [],
  "verification": "如何确认任务真的完成",
  "confidence": 0.0
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
                keep_alive=(
                    REASONING_MODEL_KEEP_ALIVE
                ),
                options={
                    "num_ctx": 4096,
                    "temperature": 0,
                },
            )

            return self._extract_json(
                response.message.content
            )

        except Exception:
            return None

    @staticmethod
    def _normalize_capabilities(
        values,
    ):
        allowed = {
            "screen_read",
            "window_read",
            "file_read",
            "window_control",
            "mouse",
            "keyboard",
            "scroll",
            "app_launch",
            "power_control",
            "file_write",
            "file_move",
            "file_delete",
        }

        result = []

        for value in (
            values
            if isinstance(
                values,
                list,
            )
            else []
        ):
            value = str(value).strip()

            if (
                value in allowed
                and value not in result
            ):
                result.append(
                    value
                )

        return result

    def record_success(
        self,
        *,
        intent,
        user_goal,
        plan_steps,
        tool_results,
        verifier_result,
        used_capabilities,
    ):
        """
        成功任务结束后调用。
        """
        if intent in {
            "chat",
            "memory",
        }:
            return None

        skill = self._derive_skill(
            intent=intent,
            user_goal=user_goal,
            plan_steps=plan_steps,
            tool_results=tool_results,
            verifier_result=verifier_result,
        )

        if not skill:
            return None

        if not bool(
            skill.get(
                "learn",
                False,
            )
        ):
            return None

        try:
            confidence = float(
                skill.get(
                    "confidence",
                    0,
                )
            )
        except Exception:
            confidence = 0.0

        if confidence < 0.78:
            return None

        key = self._safe_name(
            skill.get(
                "skill_key",
                skill.get(
                    "name",
                    "skill",
                ),
            )
        )

        learned_caps = (
            self._normalize_capabilities(
                skill.get(
                    "required_capabilities",
                    [],
                )
            )
        )

        actual_caps = set(
            str(x)
            for x in (
                used_capabilities
                or []
            )
        )

        # 学习出的 capability 不能超过真实任务使用过的。
        learned_caps = [
            cap
            for cap in learned_caps
            if cap in actual_caps
        ]

        skill_data = {
            "skill_key": key,
            "name": str(
                skill.get(
                    "name",
                    key,
                )
            ).strip(),
            "description": str(
                skill.get(
                    "description",
                    "",
                )
            ).strip(),
            "triggers": [
                str(x).strip()
                for x in skill.get(
                    "triggers",
                    []
                )
                if str(x).strip()
            ][:10],
            "parameters": [
                str(x).strip()
                for x in skill.get(
                    "parameters",
                    []
                )
                if str(x).strip()
            ][:12],
            "steps": [
                str(x).strip()
                for x in skill.get(
                    "steps",
                    []
                )
                if str(x).strip()
            ][:16],
            "required_capabilities": (
                learned_caps
            ),
            "verification": str(
                skill.get(
                    "verification",
                    "",
                )
            ).strip(),
            "safety": (
                "Skill 仅提供经验流程，"
                "每次执行仍必须经过 Task Permit。"
            ),
            "source": "learned_from_success",
            "success_count": 1,
            "last_updated": time.time(),
        }

        state = self._load_state()

        fingerprints = state.setdefault(
            "fingerprints",
            {},
        )

        record = fingerprints.get(
            key,
            {
                "success_count": 0,
            },
        )

        record[
            "success_count"
        ] = int(
            record.get(
                "success_count",
                0,
            )
        ) + 1

        record[
            "last_updated"
        ] = time.time()

        fingerprints[
            key
        ] = record

        self._save_state(
            state
        )

        skill_data[
            "success_count"
        ] = record[
            "success_count"
        ]

        candidate_path = (
            CANDIDATE_DIR
            / f"{key}.json"
        )

        candidate_path.write_text(
            json.dumps(
                skill_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            f"\n[技能学习] 候选技能："
            f"{skill_data['name']} "
            f"({skill_data['success_count']}/"
            f"{self.min_successes})"
        )

        if (
            skill_data[
                "success_count"
            ]
            >= self.min_successes
        ):
            learned_path = (
                LEARNED_DIR
                / f"{key}.json"
            )

            learned_path.write_text(
                json.dumps(
                    skill_data,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            print(
                f"[技能学习] 已晋升为长期技能："
                f"{skill_data['name']}"
            )

            return {
                "status": "learned",
                "path": str(
                    learned_path
                ),
                "skill": skill_data,
            }

        return {
            "status": "candidate",
            "path": str(
                candidate_path
            ),
            "skill": skill_data,
        }
