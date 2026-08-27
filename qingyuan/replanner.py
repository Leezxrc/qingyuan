from dataclasses import dataclass


@dataclass
class RecoveryDecision:
    should_retry: bool
    strategy: str
    note: str


class Replanner:
    """
    通用失败恢复策略。

    不扩大用户原始任务范围，
    不增加未授权 capability，
    只在当前许可证范围内换一种执行方式。
    """

    def decide(
        self,
        intent: str,
        tool_name: str,
        result: str,
        retry_count: int,
    ) -> RecoveryDecision:

        text = str(result)

        if retry_count >= 2:
            return RecoveryDecision(
                False,
                "",
                "同一步已重试两次，停止自动恢复。",
            )

        # 窗口失焦：优先恢复同一授权窗口
        if any(x in text for x in [
            "不在前台",
            "目标窗口已不在前台",
            "无法恢复到已授权窗口",
        ]):
            return RecoveryDecision(
                True,
                "refocus_same_target",
                "重新聚焦同一已授权窗口后重试。",
            )

        # 视觉定位失败：重新截图后再定位
        if any(x in text for x in [
            "视觉定位失败",
            "没有可靠找到",
            "置信度不足",
            "无法定位",
        ]):
            return RecoveryDecision(
                True,
                "recapture_and_relocate",
                "重新截取当前授权窗口，再做一次局部定位。",
            )

        # Chrome 搜索失败：重新聚焦后再走确定性快捷键
        if (
            intent == "browser_search"
            and tool_name != "browser_search_new_tab"
            and "失败" in text
        ):
            return RecoveryDecision(
                True,
                "browser_deterministic_search",
                "优先使用 browser_search_new_tab 确定性搜索。",
            )

        return RecoveryDecision(
            False,
            "",
            "没有安全的自动恢复策略。",
        )
