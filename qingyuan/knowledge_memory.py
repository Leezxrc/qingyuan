import json
import re
import threading
from pathlib import Path

from ollama import chat

from .config import (
    MODEL,
    REASONING_MODEL_KEEP_ALIVE,
)


KNOWLEDGE_DIR = Path(
    r"C:\MyAgent\data\knowledge"
)

ENTITIES_FILE = (
    KNOWLEDGE_DIR
    / "entities.json"
)

PREFERENCES_FILE = (
    KNOWLEDGE_DIR
    / "preferences.json"
)

LOCATIONS_FILE = (
    KNOWLEDGE_DIR
    / "locations.json"
)

GENERAL_FILE = (
    KNOWLEDGE_DIR
    / "general.json"
)


class KnowledgeMemory:
    """
    清渊的自然语言长期知识库。

    支持：
    - 记住 X 是 Y
    - 把 X 改成 Y
    - 忘记 X
    - X 是什么
    - 在已知实体上做后续任务

    写入的是清渊自己的 data\\knowledge，
    不等于获得任何电脑操作权限。
    """

    FILES = {
        "entity": ENTITIES_FILE,
        "preference": PREFERENCES_FILE,
        "location": LOCATIONS_FILE,
        "general": GENERAL_FILE,
    }

    def __init__(
        self,
        model_router,
    ):
        self.model_router = model_router
        self._lock = threading.RLock()
        self._ensure()

    def _ensure(self):
        KNOWLEDGE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        for path in self.FILES.values():
            if not path.exists():
                path.write_text(
                    "{}",
                    encoding="utf-8",
                )

    @staticmethod
    def _safe_load(path):
        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            return (
                data
                if isinstance(data, dict)
                else {}
            )
        except Exception:
            return {}

    @staticmethod
    def _safe_save(path, data):
        path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
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
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
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
            obj = json.loads(
                match.group(0)
            )
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    @staticmethod
    def _contains_sensitive(text):
        lower = str(text).lower()

        forbidden = [
            "password",
            "密码",
            "api key",
            "apikey",
            "私钥",
            "银行卡",
            "信用卡",
            "身份证",
            "access token",
            "refresh token",
        ]

        return any(
            item in lower
            for item in forbidden
        )

    @staticmethod
    def _normalize_value(
        kind,
        entity_type,
        value,
    ):
        """
        标准化长期关系的 value。

        微信聊天只存真正可搜索的聊天名/群号，
        不把“微信群/微信群聊/群聊”这些类型词存进名字。
        """
        value = str(value).strip()

        if entity_type == "wechat_chat":
            value = re.sub(
                r"^(?:微信)?群(?:聊)?\s*",
                "",
                value,
            )

            value = re.sub(
                r"^微信聊天\s*",
                "",
                value,
            )

            value = value.strip()

        return value

    def remember_teaching_rule(
        self,
        text,
    ):
        """
        保存用户明确教给清渊的做事规则。

        不申请电脑权限。
        """
        raw = str(text).strip()

        if not raw:
            return "没有识别到需要学习的规则。"

        if self._contains_sensitive(
            raw
        ):
            return (
                "这条规则可能包含不适合长期保存的敏感内容，"
                "我没有保存。"
            )

        path = self.FILES[
            "preference"
        ]

        key_base = raw[:40].strip()

        # 让常见教学语句形成更稳定的 key。
        if (
            "微信"
            in raw
            and "搜索"
            in raw
            and "群"
            in raw
        ):
            key = "微信搜索群聊名称规则"
        else:
            key = (
                "经验规则："
                + key_base
            )

        with self._lock:
            data = self._safe_load(
                path
            )

            data[key] = {
                "value": raw,
                "entity_type": (
                    "instruction_rule"
                ),
                "aliases": [],
            }

            self._safe_save(
                path,
                data,
            )

        return (
            f"记住了这条经验规则：{raw}"
        )

    def _parse_command(
        self,
        text,
    ):
        """
        用强模型只做结构解析，不执行工具。
        """
        selected_model = (
            self.model_router
            .for_semantic_interpretation()
        )

        prompt = f"""
你是个人本地智能体的长期记忆解析器。

分析用户这句话属于：
remember = 新增/记住关系
update = 修改已有关系
forget = 忘记/删除
query = 查询已记住关系
none = 不是记忆管理

可选 kind：
entity = 人、群聊、设备、软件实体别名
preference = 默认选择、习惯、偏好
location = 文件夹、路径、资源位置
general = 其他普通关系

如果是微信聊天/群聊，entity_type 写 wechat_chat。
如果是软件别名，entity_type 写 app。
如果是路径，kind 使用 location。

规则：
1. 不凭空补信息。
2. 数字、路径、软件名必须保持原样。
3. “记住家庭群就是微信群聊9652711”
   应解析为：
   action=remember
   kind=entity
   key=家庭群
   value=9652711
   entity_type=wechat_chat
4. “把家庭群改成微信群聊888888”
   action=update
5. “忘记家庭群”
   action=forget
6. “家庭群是哪个？”
   action=query
7. 普通执行命令如“在家庭群里发消息”必须 action=none。

用户：
{text}

严格只返回 JSON：
{{
  "action":"remember|update|forget|query|none",
  "kind":"entity|preference|location|general",
  "key":"",
  "value":"",
  "entity_type":"",
  "aliases":[],
  "confidence":0.0
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

            if data:
                return data

        except Exception:
            pass

        return {
            "action": "none",
            "kind": "general",
            "key": "",
            "value": "",
            "entity_type": "",
            "aliases": [],
            "confidence": 0.0,
        }

    def _all_records(self):
        result = []

        for kind, path in self.FILES.items():
            data = self._safe_load(
                path
            )

            for key, item in data.items():
                if isinstance(item, dict):
                    record = dict(item)
                else:
                    record = {
                        "value": item
                    }

                record["key"] = key
                record["kind"] = kind

                result.append(
                    record
                )

        return result

    def _direct_query_known_relation(
        self,
        text,
    ):
        """
        已知关系查询走确定性路径，不交给 Router 猜。

        支持正向：
        - 家庭群是什么
        - 家庭群叫什么
        - 家庭群是哪个
        - 你还记得家庭群吗

        支持反向：
        - 微信群9652711是我的什么群
        - 9652711是什么群
        - 9652711对应哪个群

        只读取本地 knowledge，不需要任何电脑权限。
        """
        raw = str(text).strip()

        query_cues = [
            "叫什么",
            "叫啥",
            "叫什麼",
            "是什么",
            "是什麼",
            "是哪个",
            "是哪一个",
            "是哪個",
            "什么群",
            "什麼群",
            "哪个群",
            "哪個群",
            "对应什么",
            "對應什麼",
            "对应哪个",
            "對應哪個",
            "名字是什么",
            "名字叫啥",
            "名称是什么",
            "名称叫啥",
            "你还记得",
            "你還記得",
            "你记得",
            "你記得",
            "还记得",
            "還記得",
        ]

        if not any(
            cue in raw
            for cue in query_cues
        ):
            return None

        records = self._all_records()

        # ------------------------------------------------
        # 1. 正向：key / alias 出现在问题中
        # ------------------------------------------------
        forward = []

        for record in records:
            key = str(
                record.get(
                    "key",
                    "",
                )
            ).strip()

            value = str(
                record.get(
                    "value",
                    "",
                )
            ).strip()

            aliases = [
                str(x).strip()
                for x in record.get(
                    "aliases",
                    []
                )
                if str(x).strip()
            ]

            for name in [
                key,
                *aliases,
            ]:
                if (
                    name
                    and name in raw
                ):
                    forward.append(
                        (
                            len(name),
                            key,
                            value,
                            record,
                        )
                    )
                    break

        if forward:
            forward.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            _, key, value, record = (
                forward[0]
            )

            entity_type = str(
                record.get(
                    "entity_type",
                    "",
                )
            ).strip()

            if entity_type == "wechat_chat":
                clean_value = self._normalize_value(
                    "entity",
                    entity_type,
                    value,
                )

                return (
                    f"我记得，你的“{key}”"
                    f"对应微信聊天“{clean_value}”。"
                )

            return (
                f"我记得，“{key}”是“{value}”。"
            )

        # ------------------------------------------------
        # 2. 反向：value 出现在问题中
        #
        # 特别处理：
        # 微信群9652711是我的什么群
        # ------------------------------------------------
        reverse = []

        raw_compact = re.sub(
            r"\s+",
            "",
            raw,
        )

        for record in records:
            key = str(
                record.get(
                    "key",
                    "",
                )
            ).strip()

            value = str(
                record.get(
                    "value",
                    "",
                )
            ).strip()

            if not value:
                continue

            value_compact = re.sub(
                r"\s+",
                "",
                value,
            )

            if (
                value_compact
                and value_compact
                in raw_compact
            ):
                reverse.append(
                    (
                        len(value_compact),
                        key,
                        value,
                        record,
                    )
                )

        if reverse:
            reverse.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            _, key, value, record = (
                reverse[0]
            )

            entity_type = str(
                record.get(
                    "entity_type",
                    "",
                )
            ).strip()

            if entity_type == "wechat_chat":
                clean_value = self._normalize_value(
                    "entity",
                    entity_type,
                    value,
                )

                return (
                    f"我记得，微信聊天“{clean_value}”"
                    f"就是你的“{key}”。"
                )

            return (
                f"我记得，“{value}”"
                f"对应的是“{key}”。"
            )

        return None


    def handle_command(
        self,
        text,
    ):
        """
        如果是明确的记忆管理命令，直接处理。
        返回 None = 不是记忆管理。
        """
        raw = str(text).strip()

        # 已经保存过的关系查询优先确定性读取。
        # 这一步不调用模型、不进入 GUI Router、更不申请电脑权限。
        direct_reply = self._direct_query_known_relation(
            raw
        )

        if direct_reply is not None:
            return direct_reply

        obvious_memory_cues = [
            "记住",
            "记一下",
            "以后记得",
            "别忘了",
            "忘记",
            "忘掉",
            "不要再记",
            "改成",
            "修改成",
            "我让你记住",
            "你记得",
            "是什么",
            "是哪个",
            "是哪一个",
            "叫什么",
            "叫啥",
            "名字是什么",
            "名称是什么",
            "你还记得",
            "还记得",
            "什么群",
            "哪个群",
            "对应什么",
            "对应哪个",
        ]

        # 避免每句普通话都调用强模型。
        if not any(
            cue in raw
            for cue in obvious_memory_cues
        ):
            return None

        parsed = self._parse_command(
            raw
        )

        try:
            confidence = float(
                parsed.get(
                    "confidence",
                    0,
                )
            )
        except Exception:
            confidence = 0.0

        action = str(
            parsed.get(
                "action",
                "none",
            )
        )

        if (
            action == "none"
            or confidence < 0.75
        ):
            return None

        kind = str(
            parsed.get(
                "kind",
                "general",
            )
        )

        if kind not in self.FILES:
            kind = "general"

        key = str(
            parsed.get(
                "key",
                "",
            )
        ).strip()

        value = str(
            parsed.get(
                "value",
                "",
            )
        ).strip()

        entity_type = str(
            parsed.get(
                "entity_type",
                "",
            )
        ).strip()

        aliases = [
            str(x).strip()
            for x in parsed.get(
                "aliases",
                []
            )
            if str(x).strip()
        ]

        if action in {
            "remember",
            "update",
        }:
            value = self._normalize_value(
                kind,
                entity_type,
                value,
            )

            if (
                not key
                or not value
            ):
                return (
                    "我理解你是想让我记住一条关系，"
                    "但还没有识别出完整的名称和值。"
                )

            if self._contains_sensitive(
                raw
            ):
                return (
                    "这条内容可能包含不适合明文长期保存的敏感信息，"
                    "我没有保存。"
                )

            path = self.FILES[
                kind
            ]

            with self._lock:
                data = self._safe_load(
                    path
                )

                data[key] = {
                    "value": value,
                    "entity_type": entity_type,
                    "aliases": aliases,
                }

                self._safe_save(
                    path,
                    data,
                )

            if action == "update":
                return (
                    f"已经把“{key}”更新为“{value}”。"
                )

            return (
                f"记住了：“{key}”就是“{value}”。"
            )

        if action == "forget":
            if not key:
                return "你想让我忘记哪一条？"

            removed = []

            with self._lock:
                for kind_name, path in self.FILES.items():
                    data = self._safe_load(
                        path
                    )

                    keys_to_remove = []

                    for stored_key, item in data.items():
                        aliases_here = []

                        if isinstance(
                            item,
                            dict,
                        ):
                            aliases_here = [
                                str(x)
                                for x in item.get(
                                    "aliases",
                                    []
                                )
                            ]

                        if (
                            key == stored_key
                            or key in aliases_here
                            or key in stored_key
                        ):
                            keys_to_remove.append(
                                stored_key
                            )

                    for stored_key in keys_to_remove:
                        removed.append(
                            stored_key
                        )
                        data.pop(
                            stored_key,
                            None,
                        )

                    if keys_to_remove:
                        self._safe_save(
                            path,
                            data,
                        )

            if not removed:
                return (
                    f"我没有找到“{key}”对应的长期记忆。"
                )

            return (
                "已经忘记："
                + "、".join(
                    removed
                )
                + "。"
            )

        if action == "query":
            if not key:
                return None

            matches = self.find(
                key
            )

            if not matches:
                return (
                    f"我目前没有记住“{key}”对应的关系。"
                )

            best = matches[0]

            return (
                f"我记得“{best['key']}”是“{best['value']}”。"
            )

        return None

    def find(
        self,
        keyword,
    ):
        keyword = str(
            keyword
        ).strip()

        matches = []

        for record in self._all_records():
            key = str(
                record.get(
                    "key",
                    "",
                )
            )

            value = str(
                record.get(
                    "value",
                    "",
                )
            )

            aliases = [
                str(x)
                for x in record.get(
                    "aliases",
                    []
                )
            ]

            if (
                keyword == key
                or keyword in key
                or keyword == value
                or keyword in aliases
            ):
                matches.append(
                    record
                )

        matches.sort(
            key=lambda x: (
                0
                if x["key"] == keyword
                else 1
            )
        )

        return matches

    def resolve_references(
        self,
        text,
    ):
        """
        将已知实体/路径别名解析成执行层更明确的表达。

        例：
        在家庭群里发送你好
        ->
        在微信群聊9652711里发送你好
        """
        result = str(text)

        records = self._all_records()

        # 长别名优先，减少短词误替换。
        candidates = []

        for record in records:
            key = str(
                record.get(
                    "key",
                    "",
                )
            ).strip()

            value = str(
                record.get(
                    "value",
                    "",
                )
            ).strip()

            entity_type = str(
                record.get(
                    "entity_type",
                    "",
                )
            ).strip()

            names = [
                key
            ]

            names.extend(
                [
                    str(x).strip()
                    for x in record.get(
                        "aliases",
                        []
                    )
                    if str(x).strip()
                ]
            )

            for name in set(names):
                if name and name in result:
                    candidates.append(
                        (
                            len(name),
                            name,
                            value,
                            entity_type,
                            record.get(
                                "kind",
                                "",
                            ),
                        )
                    )

        candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        replacements = []

        for _, name, value, entity_type, kind in candidates:
            if name not in result:
                continue

            if entity_type == "wechat_chat":
                clean_value = (
                    self._normalize_value(
                        "entity",
                        entity_type,
                        value,
                    )
                )

                replacement = (
                    f"微信群聊{clean_value}"
                )

            elif entity_type == "app":
                replacement = value

            elif kind == "location":
                replacement = value

            else:
                # 普通关系不自动改写执行命令，
                # 只进入 memory_context。
                continue

            result = result.replace(
                name,
                replacement,
            )

            replacements.append(
                (
                    name,
                    replacement,
                )
            )

        return result, replacements

    def relevant_context(
        self,
        query,
        limit=8,
    ):
        """
        只返回当前问题相关的结构化长期知识，
        避免把整个知识库都塞进模型上下文。
        """
        raw = str(query).lower()

        records = self._all_records()

        scored = []

        for record in records:
            key = str(
                record.get(
                    "key",
                    "",
                )
            )

            value = str(
                record.get(
                    "value",
                    "",
                )
            )

            aliases = [
                str(x)
                for x in record.get(
                    "aliases",
                    []
                )
            ]

            score = 0

            if key and key.lower() in raw:
                score += 10

            if value and value.lower() in raw:
                score += 6

            for alias in aliases:
                if alias and alias.lower() in raw:
                    score += 8

            # 中文短关键词重合
            for token in [
                key,
                value,
                *aliases,
            ]:
                if (
                    token
                    and len(token) >= 2
                    and token[:2].lower()
                    in raw
                ):
                    score += 1

            if (
                record.get(
                    "entity_type"
                )
                == "instruction_rule"
            ):
                rule_value = str(
                    record.get(
                        "value",
                        "",
                    )
                ).lower()

                # 微信/搜索/群聊等关键词与规则重合时提高优先级。
                for token in [
                    "微信",
                    "搜索",
                    "群",
                    "浏览器",
                    "文件",
                    "发送",
                ]:
                    if (
                        token in raw
                        and token in rule_value
                    ):
                        score += 4

            if score > 0:
                scored.append(
                    (
                        score,
                        record,
                    )
                )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        if not scored:
            return "没有发现与当前问题直接相关的长期知识。"

        lines = []

        for _, record in scored[:limit]:
            key = str(
                record.get(
                    "key",
                    "",
                )
            )

            value = str(
                record.get(
                    "value",
                    "",
                )
            )

            entity_type = str(
                record.get(
                    "entity_type",
                    "",
                )
            )

            suffix = (
                f" [{entity_type}]"
                if entity_type
                else ""
            )

            lines.append(
                f"- {key} = {value}{suffix}"
            )

        return "\\n".join(
            lines
        )

    def context_text(self):
        records = self._all_records()

        if not records:
            return (
                "目前没有结构化长期知识。"
            )

        lines = []

        for record in records[:40]:
            key = str(
                record.get(
                    "key",
                    "",
                )
            )

            value = str(
                record.get(
                    "value",
                    "",
                )
            )

            entity_type = str(
                record.get(
                    "entity_type",
                    "",
                )
            )

            suffix = (
                f" [{entity_type}]"
                if entity_type
                else ""
            )

            lines.append(
                f"- {key} = {value}{suffix}"
            )

        return "\n".join(
            lines
        )
