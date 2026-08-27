from dataclasses import dataclass


@dataclass
class VerificationResult:
    success: bool
    reason: str


class Verifier:
    """
    任务完成验证器。

    不根据模型“说自己完成了”判断；
    只看真实工具动作、任务状态和工具结果。
    """

    def __init__(self, runtime):
        self.runtime = runtime

    def verify(
        self,
        plan,
        tool_results: list[tuple[str, str]],
    ) -> VerificationResult:

        names = [
            name
            for name, _ in tool_results
        ]

        results = [
            str(result)
            for _, result in tool_results
        ]

        failure_markers = [
            "失败",
            "拒绝",
            "没有找到",
            "不存在",
            "权限不足",
            "没有获得",
            "无法",
            "超出本次任务",
            "已停止",
        ]

        # 如果最后几个关键工具结果明确失败，不允许宣布成功。
        for result in results[-5:]:
            if any(
                marker in result
                for marker in failure_markers
            ):
                return VerificationResult(
                    False,
                    result[:300],
                )

        mode = plan.verify_mode

        if mode == "browser_action":
            if "browser_search_new_tab" in names:
                return VerificationResult(
                    True,
                    "已检测到真实的新标签页搜索动作。",
                )
            return VerificationResult(
                False,
                "没有检测到 browser_search_new_tab 真实执行记录。",
            )

        if mode == "foreground":
            if any(
                name in names
                for name in [
                    "bring_app_to_foreground",
                    "focus_window",
                ]
            ):
                return VerificationResult(
                    True,
                    "已检测到真实窗口前台切换工具。",
                )
            return VerificationResult(
                False,
                "没有检测到窗口切换工具执行。",
            )

        if mode == "wechat_visual":
            wechat_results = [
                str(result)
                for name, result in tool_results
                if name == "wechat_send_message"
            ]

            if not wechat_results:
                return VerificationResult(
                    False,
                    "没有检测到微信发送工具执行。",
                )

            last = wechat_results[-1]

            # 微信发送是否完成，以专用工具的真实执行结果为准。
            # 不再强制要求旧版特定文案：
            # “已真实执行微信发送动作 + 当前屏幕视觉分析”
            #
            # 否则会出现：
            # 实际消息已经发送成功，但 Verifier 因文案格式不同误判失败。
            wechat_failure_markers = [
                "失败",
                "拒绝",
                "没有找到",
                "不存在",
                "权限不足",
                "没有获得",
                "无法",
                "已停止",
                "NO_MATCH",
                "SENT_UNCERTAIN",
                "不确定",
            ]

            if any(
                marker in last
                for marker in wechat_failure_markers
            ):
                return VerificationResult(
                    False,
                    last[:300],
                )

            success_markers = [
                "微信消息已执行发送",
                "微信发送动作已真实执行",
                "已真实执行微信发送动作",
                "已成功在微信群聊",
            ]

            if any(
                marker in last
                for marker in success_markers
            ):
                return VerificationResult(
                    True,
                    "已检测到微信专用发送工具的真实成功结果。",
                )

            # 兜底：
            # 专用发送工具已执行，且没有任何明确失败标记，
            # 视为工具层成功，避免再次出现假阴性。
            return VerificationResult(
                True,
                "微信发送工具已执行，且未发现明确失败标记。",
            )

        if mode in {
            "file_result",
            "launch_result",
            "tool_result",
        }:
            if tool_results:
                return VerificationResult(
                    True,
                    "存在真实工具执行结果，未发现明确失败。",
                )
            return VerificationResult(
                False,
                "没有任何真实工具执行结果。",
            )

        if mode == "gui_visual":
            actions = self.runtime.desktop_action_types()

            if actions:
                return VerificationResult(
                    True,
                    "检测到真实桌面动作记录。",
                )

            return VerificationResult(
                False,
                "没有检测到真实桌面动作。",
            )

        return VerificationResult(
            True,
            "无需额外验证。",
        )
