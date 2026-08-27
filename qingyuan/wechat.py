import json
import time

from .wechat_capture import WeChatCapture
from .wechat_template import WeChatTemplate
from .experience_library import WeChatExperienceLibrary


class WeChatTools:
    def __init__(self, runtime, desktop, vision):
        self.runtime = runtime
        self.desktop = desktop
        self.vision = vision
        self.capture = WeChatCapture(
            runtime
        )
        self.template = WeChatTemplate()
        self.experience = WeChatExperienceLibrary()

    def _ensure_wechat_foreground(self):
        if self.desktop.desktop_target_ok():
            return True

        with self.runtime.desktop_lock:
            hwnd = self.runtime.desktop_task.get(
                "target_hwnd"
            )

        return bool(
            hwnd
            and self.desktop._force_foreground(
                int(hwnd)
            )
        )

    def _debug_capture(
        self,
        label,
    ):
        try:
            info = self.capture.capture(
                label
            )

            print(
                f"\n[微信截图] {info['path']}"
            )

            return info

        except Exception as e:
            print(
                f"\n[微信截图失败] {e}"
            )
            return None

    def _click_exact_search_result(
        self,
        chat_identifier,
    ):
        """
        只截微信左侧栏，
        精确点击搜索结果中包含目标编号/名称的那一项。
        """
        info = self.capture.capture_region(
            self.template.region(
                "search_results"
            ),
            "02_search_results_region",
        )

        located = self.vision.locate_in_image_region(
            (
                "在微信搜索结果中，找到文字"
                f"“{chat_identifier}”完全匹配的聊天/群聊结果。"
                "必须是搜索结果项本身，不要选其他聊天。"
            ),
            info["path"],
            info["rect"],
            min_confidence=0.78,
        )

        try:
            data = json.loads(
                located
            )
        except Exception:
            return (
                "无法精确定位目标搜索结果："
                + located
            )

        result = self.desktop.mouse_click(
            int(data["x"]),
            int(data["y"]),
            "left",
        )

        if not result.startswith("已在"):
            return result

        return (
            "已点击精确搜索结果："
            f"{chat_identifier}"
        )

    def _verify_current_chat_header(
        self,
        chat_identifier,
    ):
        """
        只截微信右侧顶部标题栏。
        左侧列表中的 9652711 不会进入这张截图，
        因此不能再造成假 MATCH。
        """
        info = self.capture.capture_region(
            self.template.region(
                "chat_header"
            ),
            "03_chat_header_only",
        )

        answer = self.vision.analyze_image_region(
            (
                f"当前聊天标题是否明确对应“{chat_identifier}”？"
                "只检查当前局部截图里的聊天标题文字。"
                "如果标题本身就是该数字/名称，或明确包含它，回答 EXACT_MATCH。"
                "否则回答 NO_MATCH。"
            ),
            info["path"],
            reference_image=(
                self.template.reference_image()
                if self.template.reference_exists()
                else None
            ),
        )

        upper = answer.upper()

        if "EXACT_MATCH" in upper:
            return True, answer

        return False, answer

    def wechat_send_message(
        self,
        chat_identifier: str,
        message: str,
    ) -> str:
        """
        微信发送：
        搜索 -> 精确点击搜索结果 -> 标题验证 -> 输入 -> 发送。

        所有运行截图先进入 workspace\\screenshots。
        只有最终成功后，关键局部截图才晋升到
        workspace\\wechat_debug 对应分类。
        """
        chat_identifier = str(
            chat_identifier
        ).strip()

        message = str(
            message
        ).strip()

        if not chat_identifier:
            return "缺少聊天对象或群聊标识。"

        if not message:
            return "缺少要发送的消息内容。"

        required = {
            "window_control",
            "screen_read",
            "mouse",
            "keyboard",
        }

        missing = [
            cap
            for cap in required
            if not self.desktop.permission.has(cap)
        ]

        if missing:
            return (
                "当前微信任务权限不足，缺少："
                + "、".join(
                    sorted(missing)
                )
            )

        if not self._ensure_wechat_foreground():
            return (
                "无法把已授权微信窗口恢复到前台，"
                "任务已停止。"
            )

        useful = {}

        # ----------------------------------------------------
        # 1. 搜索框
        # ----------------------------------------------------

        search_info = self.capture.capture_region(
            self.template.region(
                "search_box"
            ),
            "wechat_search_box",
        )

        useful["search_box"] = (
            search_info["path"]
        )

        located = self.vision.locate_in_image_region(
            "微信白色搜索框内部可点击区域",
            search_info["path"],
            search_info["rect"],
            min_confidence=0.70,
        )

        try:
            search_point = json.loads(
                located
            )
        except Exception:
            return (
                "无法定位微信搜索框："
                + located
            )

        result = self.desktop.mouse_click(
            int(search_point["x"]),
            int(search_point["y"]),
            "left",
        )

        if not result.startswith("已在"):
            return (
                "无法点击微信搜索框："
                + result
            )

        time.sleep(0.2)

        # ----------------------------------------------------
        # 2. 输入目标
        # ----------------------------------------------------

        result = self.desktop.keyboard_shortcut(
            ["ctrl", "a"]
        )

        if not result.startswith(
            "已执行快捷键"
        ):
            return (
                "无法选中搜索框内容："
                + result
            )

        result = self.desktop.keyboard_type(
            chat_identifier
        )

        if not result.startswith(
            "已输入"
        ):
            return (
                "无法输入聊天标识："
                + result
            )

        time.sleep(1.0)

        # ----------------------------------------------------
        # 3. 搜索结果
        # ----------------------------------------------------

        result_info = self.capture.capture_region(
            self.template.region(
                "search_results"
            ),
            "wechat_search_result",
        )

        useful["search_result"] = (
            result_info["path"]
        )

        located = self.vision.locate_in_image_region(
            (
                "在微信搜索结果中，找到文字"
                f"“{chat_identifier}”完全匹配的聊天/群聊结果。"
                "必须是搜索结果项本身，不要选其他聊天。"
            ),
            result_info["path"],
            result_info["rect"],
            min_confidence=0.78,
        )

        try:
            data = json.loads(
                located
            )
        except Exception:
            return (
                "无法精确定位目标搜索结果："
                + located
            )

        result = self.desktop.mouse_click(
            int(data["x"]),
            int(data["y"]),
            "left",
        )

        if not result.startswith("已在"):
            return result

        time.sleep(0.7)

        # ----------------------------------------------------
        # 4. 当前聊天标题
        # ----------------------------------------------------

        header_info = self.capture.capture_region(
            self.template.region(
                "chat_header"
            ),
            "wechat_chat_header",
        )

        useful["chat_header"] = (
            header_info["path"]
        )

        answer = self.vision.analyze_image_region(
            (
                f"当前聊天标题是否明确对应“{chat_identifier}”？"
                "只检查当前局部截图里的聊天标题文字。"
                "如果标题本身就是该数字/名称，或明确包含它，回答 EXACT_MATCH。"
                "否则回答 NO_MATCH。"
            ),
            header_info["path"],
            reference_image=(
                self.template.reference_image()
                if self.template.reference_exists()
                else None
            ),
        )

        if "EXACT_MATCH" not in answer.upper():
            # 有价值的失败案例可保留一张标题图。
            self.experience.promote(
                header_info["path"],
                "failures",
                label="chat_header_no_match",
            )

            return (
                "已经点击搜索结果，但右侧聊天标题"
                f"没有确认是“{chat_identifier}”。"
                "为避免发错消息，已停止。\n"
                + answer
            )

        # ----------------------------------------------------
        # 5. 消息输入框
        # ----------------------------------------------------

        message_info = self.capture.capture_region(
            self.template.region(
                "message_box"
            ),
            "wechat_message_box",
        )

        useful["message_box"] = (
            message_info["path"]
        )

        located = self.vision.locate_in_image_region(
            "微信聊天消息输入区域内部的空白可输入位置",
            message_info["path"],
            message_info["rect"],
            min_confidence=0.68,
        )

        try:
            message_point = json.loads(
                located
            )
        except Exception:
            return (
                "无法定位微信消息输入框："
                + located
            )

        result = self.desktop.mouse_click(
            int(message_point["x"]),
            int(message_point["y"]),
            "left",
        )

        if not result.startswith("已在"):
            return (
                "无法点击微信消息输入框："
                + result
            )

        time.sleep(0.2)

        # ----------------------------------------------------
        # 6. 输入并发送
        # ----------------------------------------------------

        result = self.desktop.keyboard_type(
            message
        )

        if not result.startswith(
            "已输入"
        ):
            return (
                "消息输入失败："
                + result
            )

        result = self.desktop.press_key(
            "enter"
        )

        if not result.startswith(
            "已按下"
        ):
            return (
                "发送失败："
                + result
            )

        time.sleep(0.5)

        send_info = self.capture.capture(
            "wechat_send_success"
        )

        useful["send_success"] = (
            send_info["path"]
        )

        # ----------------------------------------------------
        # 7. 最终成功后晋升经验
        # ----------------------------------------------------

        for category, path in useful.items():
            self.experience.promote(
                path,
                category,
                label=chat_identifier,
            )

        return (
            "微信消息已执行发送。"
            f"目标：{chat_identifier}；"
            f"消息：{message}"
        )
