import json
import re
from pathlib import Path


SKILLS_DIR = Path(
    r"C:\MyAgent\skills"
)

USER_SKILLS_DIR = (
    SKILLS_DIR
    / "user"
)

BUILTIN_SKILLS_DIR = (
    SKILLS_DIR
    / "builtin"
)

LEARNED_SKILLS_DIR = (
    SKILLS_DIR
    / "learned"
)


class SkillLibrary:
    """
    可复用操作技能库。

    一个 skill 只描述：
    - 何时适用
    - 推荐步骤
    - 需要哪些能力
    - 验证方式

    Skill 不授予权限。
    真正执行仍然必须经过 Task Permit。
    """

    def __init__(self):
        self._ensure_dirs()

    def _ensure_dirs(self):
        USER_SKILLS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        BUILTIN_SKILLS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        LEARNED_SKILLS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _load_json(path):
        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
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

    def all_skills(self):
        skills = []

        for directory in [
            BUILTIN_SKILLS_DIR,
            USER_SKILLS_DIR,
            LEARNED_SKILLS_DIR,
        ]:
            for path in directory.glob(
                "*.json"
            ):
                data = self._load_json(
                    path
                )

                if not data:
                    continue

                data["_path"] = str(
                    path
                )

                skills.append(
                    data
                )

        return skills

    @staticmethod
    def _score(
        query,
        skill,
    ):
        raw = str(
            query
        ).lower()

        score = 0

        name = str(
            skill.get(
                "name",
                "",
            )
        ).lower()

        description = str(
            skill.get(
                "description",
                "",
            )
        ).lower()

        triggers = [
            str(x).lower()
            for x in skill.get(
                "triggers",
                []
            )
        ]

        if name and name in raw:
            score += 8

        for trigger in triggers:
            if trigger and trigger in raw:
                score += 10

        for token in re.findall(
            r"[\u4e00-\u9fff]{2,}|[a-z0-9_]+",
            raw,
        ):
            if (
                token in description
                or token in name
            ):
                score += 1

        return score

    def match(
        self,
        query,
        limit=3,
    ):
        scored = []

        for skill in self.all_skills():
            score = self._score(
                query,
                skill,
            )

            if score > 0:
                scored.append(
                    (
                        score,
                        skill,
                    )
                )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        return [
            skill
            for _, skill in scored[
                :limit
            ]
        ]

    def context_text(
        self,
        query,
    ):
        skills = self.match(
            query,
            limit=2,
        )

        if not skills:
            return ""

        blocks = []

        for skill in skills:
            lines = [
                f"技能：{skill.get('name','')}",
                (
                    "说明："
                    + str(
                        skill.get(
                            "description",
                            "",
                        )
                    )
                ),
            ]

            steps = skill.get(
                "steps",
                [],
            )

            if isinstance(
                steps,
                list,
            ):
                lines.append(
                    "推荐步骤："
                )

                for i, step in enumerate(
                    steps,
                    1,
                ):
                    lines.append(
                        f"{i}. {step}"
                    )

            verify = skill.get(
                "verification"
            )

            if verify:
                lines.append(
                    "验证："
                    + str(verify)
                )

            caps = skill.get(
                "required_capabilities",
                [],
            )

            if caps:
                lines.append(
                    "预计能力："
                    + ", ".join(
                        str(x)
                        for x in caps
                    )
                )

            blocks.append(
                "\n".join(lines)
            )

        return "\n\n".join(
            blocks
        )
