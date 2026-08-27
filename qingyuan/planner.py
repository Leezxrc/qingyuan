from dataclasses import dataclass, field
import json
import re

from ollama import chat

from .config import (
    MODEL,
    REASONING_MODEL_NUM_CTX,
    REASONING_MODEL_KEEP_ALIVE,
)


@dataclass
class TaskPlan:
    intent: str
    goal: str
    steps: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    verify_mode: str = "tool_result"

    def as_prompt_text(self) -> str:
        lines = [
            "【内部任务计划】",
            f"目标：{self.goal}",
            "步骤：",
        ]

        for index, step in enumerate(self.steps, 1):
            lines.append(f"{index}. {step}")

        if self.required_capabilities:
            lines.append(
                "预计所需权限："
                + ", ".join(self.required_capabilities)
            )

        if self.targets:
            lines.append(
                "预计目标："
                + ", ".join(self.targets)
            )

        lines.append(
            f"验证方式：{self.verify_mode}"
        )

        return "\n".join(lines)


class Planner:
    def __init__(
        self,
        model_router,
    ):
        self.model_router = model_router

    """
    轻量 Planner。

    它不操作电脑，也不决定“允许不允许”。
    只把用户原始命令拆成可执行步骤，供 Executor 使用。

    常见任务使用确定性计划，避免为了规划再额外调用大模型。
    """

    def _refine_complex_plan(
        self,
        plan: TaskPlan,
    ) -> TaskPlan:
        """
        只让强模型优化“步骤顺序/拆解”，
        不允许它扩大 capability、target 或 goal。
        """
        selected_model = (
            self.model_router.for_planning()
        )

        if selected_model == MODEL:
            return plan

        prompt = f"""
你是本地电脑智能体的任务规划器。

用户目标：
{plan.goal}

当前 intent：
{plan.intent}

已经由安全层确定：
允许涉及的能力只能来自：
{plan.required_capabilities}

允许目标只能来自：
{plan.targets}

当前基础步骤：
{plan.steps}

你的任务：
只优化步骤的顺序、拆分和失败后的安全检查。
禁止新增 capability。
禁止新增 target。
禁止改变用户目标。
禁止执行任何工具。

严格只返回 JSON：
{{
  "steps": ["步骤1","步骤2",...]
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
                    "num_ctx": min(
                        REASONING_MODEL_NUM_CTX,
                        4096,
                    ),
                    "temperature": 0,
                },
            )

            raw = (
                response.message.content
                .strip()
            )

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

            data = json.loads(raw)

            steps = data.get(
                "steps",
                [],
            )

            if (
                isinstance(steps, list)
                and 1 <= len(steps) <= 12
            ):
                cleaned = [
                    str(step).strip()
                    for step in steps
                    if str(step).strip()
                ]

                if cleaned:
                    plan.steps = cleaned

        except Exception:
            # 规划增强失败时，保留确定性基础计划。
            pass

        return plan

    def create(self, intent: str, user_input: str) -> TaskPlan:
        plan = self._create_base(
            intent,
            user_input,
        )

        if intent in {
            "filesystem",
            "app_launch",
            "foreground",
            "browser_search",
            "wechat_send",
            "gui",
        }:
            return self._refine_complex_plan(
                plan
            )

        return plan

    def _create_base(
        self,
        intent: str,
        user_input: str,
    ) -> TaskPlan:
        text = str(user_input).strip()

        if intent == "system_info":
            return TaskPlan(
                intent=intent,
                goal=text,
                steps=[
                    "调用只读系统信息工具获取真实数据",
                    "根据工具返回结果直接回答用户",
                ],
                required_capabilities=[],
                targets=[],
                verify_mode="none",
            )

        if intent == "browser_search":
            return TaskPlan(
                intent=intent,
                goal=text,
                steps=[
                    "绑定已打开的 Chrome 窗口",
                    "申请本任务需要的窗口控制与键盘权限",
                    "在新标签页提交用户指定搜索内容",
                    "确认搜索动作真实执行",
                    "释放本任务权限",
                ],
                required_capabilities=[
                    "window_read",
                    "window_control",
                    "keyboard",
                ],
                targets=["Chrome"],
                verify_mode="browser_action",
            )

        if intent == "foreground":
            return TaskPlan(
                intent=intent,
                goal=text,
                steps=[
                    "找到用户指定的已运行窗口",
                    "申请窗口控制权限",
                    "把目标窗口切换到前台",
                    "验证真实前台窗口",
                    "释放权限",
                ],
                required_capabilities=[
                    "window_read",
                    "window_control",
                ],
                targets=self._extract_app_targets(text),
                verify_mode="foreground",
            )

        if intent == "wechat_send":
            chat, message = self._extract_wechat_parts(text)

            targets = ["微信"]
            if chat:
                targets.append(chat)

            return TaskPlan(
                intent=intent,
                goal=text,
                steps=[
                    "绑定微信窗口",
                    "申请窗口、屏幕、鼠标与键盘权限",
                    "搜索并进入用户指定聊天",
                    "定位消息输入区域",
                    "输入用户原命令中的消息",
                    "发送消息",
                    "视觉确认目标聊天与最新消息",
                    "释放权限",
                ],
                required_capabilities=[
                    "window_read",
                    "window_control",
                    "screen_read",
                    "mouse",
                    "keyboard",
                ],
                targets=targets,
                verify_mode="wechat_visual",
            )

        if intent == "filesystem":
            caps = ["file_read"]

            if any(x in text for x in [
                "写入", "创建", "新建", "保存", "修改",
            ]):
                caps.append("file_write")

            if any(x in text for x in [
                "移动", "重命名", "改名",
            ]):
                caps.append("file_move")

            if any(x in text for x in [
                "删除", "删掉", "清理掉",
            ]):
                caps.append("file_delete")

            if any(x in text for x in [
                "打开", "查看",
            ]):
                if "app_launch" not in caps:
                    caps.append("app_launch")

            return TaskPlan(
                intent=intent,
                goal=text,
                steps=[
                    "识别用户明确指定的文件或目录",
                    "只申请完成原始命令所需的文件权限",
                    "执行文件读取/写入/移动/删除/打开",
                    "根据真实工具结果验证",
                    "释放权限",
                ],
                required_capabilities=caps,
                targets=self._extract_path_targets(text),
                verify_mode="file_result",
            )

        if intent == "app_launch":
            return TaskPlan(
                intent=intent,
                goal=text,
                steps=[
                    "识别用户指定的程序",
                    "申请程序启动权限",
                    "启动指定程序",
                    "确认启动工具成功",
                    "释放权限",
                ],
                required_capabilities=["app_launch"],
                targets=self._extract_app_targets(text),
                verify_mode="launch_result",
            )

        if intent == "gui":
            return TaskPlan(
                intent=intent,
                goal=text,
                steps=[
                    "识别目标程序或窗口",
                    "申请本任务实际需要的临时权限",
                    "读取必要的当前界面状态",
                    "执行点击/输入/滚动/窗口切换",
                    "观察执行后的界面变化",
                    "确认目标完成",
                    "释放权限",
                ],
                required_capabilities=[
                    "window_read",
                    "window_control",
                    "screen_read",
                    "mouse",
                    "keyboard",
                ],
                targets=self._extract_app_targets(text),
                verify_mode="gui_visual",
            )

        return TaskPlan(
            intent=intent,
            goal=text,
            steps=["直接回答用户"],
            required_capabilities=[],
            targets=[],
            verify_mode="none",
        )

    @staticmethod
    def _extract_path_targets(text: str) -> list[str]:
        # 只做提示性抽取，不作为真正权限依据。
        # 真正权限 target 仍由 Permit 确认。
        patterns = [
            r"[A-Za-z]:\\[^，。！？\n]+",
            r"(?:桌面|下载|文档|Documents|Downloads|Desktop)",
        ]

        found = []
        for pattern in patterns:
            for item in re.findall(pattern, text, flags=re.I):
                item = str(item).strip(" ，。！？")
                if item and item not in found:
                    found.append(item)

        return found[:8]

    @staticmethod
    def _extract_app_targets(text: str) -> list[str]:
        known = [
            "Chrome",
            "微信",
            "QQ",
            "Discord",
            "Steam",
            "资源管理器",
            "记事本",
            "计算器",
        ]

        lower = text.lower()
        result = []

        for app in known:
            if app.lower() in lower:
                result.append(app)

        return result

    @staticmethod
    def _extract_wechat_parts(text: str):
        chat = ""

        match = re.search(
            r"(?:微信群聊|微信群|群聊)\s*([A-Za-z0-9_\-一-龥]+)",
            text,
        )

        # 如果经过语义纠错仍残留少量汉字噪声，
        # 优先提取紧邻“微信/群聊”附近的数字群号，
        # 例如“微信群条9652711” -> 9652711。
        numeric_match = re.search(
            r"(?:微信|群聊|微信群)[^\d]{0,4}(\d{4,})",
            text,
        )

        if numeric_match:
            chat = numeric_match.group(1)
        elif match:
            chat = match.group(1)
        message = ""
        quoted = re.findall(
            r"[“\"']([^”\"']+)[”\"']",
            text,
        )
        if quoted:
            message = quoted[-1]
        else:
            match = re.search(
                r"(?:发送|发一句|发一条|发消息)\s*(?:一句|一条)?\s*([^，。！？]+)$",
                text,
            )
            if match:
                message = match.group(1).strip()

        return chat, message
