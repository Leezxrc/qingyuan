import base64
import json
import re
import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab
from ollama import chat, generate

from .ipc_config import BACKEND_URL
from .ipc_http import post_json

from .config import (
    MODEL,
    VISION_MODEL,
    VISION_NUM_CTX,
    VISION_MAX_IMAGE_EDGE,
    WORKSPACE,
)
from .desktop import user32


class VisionService:
    def __init__(self, runtime, desktop, permission):
        self.runtime = runtime
        self.desktop = desktop
        self.permission = permission

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
    def _resolve_locator_point(
        data,
        image_width,
        image_height,
    ):
        """
        兼容 3 种 VLM 输出：

        1. 直接像素：
           {"x": 420, "y": 88}

        2. bbox：
           {"bbox": [x1,y1,x2,y2]}

        3. 0~1000 归一化坐标：
           x/y 或 bbox 中的数值明显超出当前图像，
           但全部落在 0~1000，则按千分比缩放。
        """

        if not isinstance(data, dict):
            return None

        # ---------------- bbox ----------------
        bbox = data.get("bbox")

        if (
            isinstance(bbox, list)
            and len(bbox) == 4
        ):
            try:
                x1, y1, x2, y2 = [
                    float(v)
                    for v in bbox
                ]
            except Exception:
                x1 = y1 = x2 = y2 = None

            if x1 is not None:
                max_value = max(
                    abs(x1),
                    abs(y1),
                    abs(x2),
                    abs(y2),
                )

                # 0~1000 normalized bbox
                if (
                    max_value <= 1000
                    and (
                        x2 > image_width
                        or y2 > image_height
                    )
                ):
                    x1 = (
                        x1 / 1000.0
                        * image_width
                    )
                    x2 = (
                        x2 / 1000.0
                        * image_width
                    )
                    y1 = (
                        y1 / 1000.0
                        * image_height
                    )
                    y2 = (
                        y2 / 1000.0
                        * image_height
                    )

                x = (x1 + x2) / 2.0
                y = (y1 + y2) / 2.0

                return x, y

        # ---------------- x/y ----------------
        try:
            x = float(data["x"])
            y = float(data["y"])
        except Exception:
            return None

        # VLM 常用 0~1000 normalized coordinates
        if (
            0 <= x <= 1000
            and 0 <= y <= 1000
            and (
                x >= image_width
                or y >= image_height
            )
        ):
            x = (
                x / 1000.0
                * image_width
            )
            y = (
                y / 1000.0
                * image_height
            )

        return x, y

    @staticmethod
    def _unload(model):
        try:
            generate(model=model, prompt="", keep_alive=0)
        except Exception:
            pass

    def _prepare(self):
        # v5.3 起 Frontend 不再运行视觉模型。
        print(
            "\n[视觉] 已捕获当前界面，"
            "正在交给 Brain Backend 分析……"
        )

    def _finish(self):
        # Backend 负责卸载视觉模型。
        print(
            "[视觉] Backend 视觉分析结束。"
        )

    def _remote_vision_chat(
        self,
        prompt,
        image_paths,
    ):
        images = []

        for path in image_paths:
            try:
                raw = Path(
                    str(path)
                ).read_bytes()

                images.append(
                    base64.b64encode(
                        raw
                    ).decode(
                        "ascii"
                    )
                )

            except Exception as e:
                raise RuntimeError(
                    f"无法读取视觉截图：{e}"
                )

        response = post_json(
            BACKEND_URL
            + "/vision/infer",
            {
                "prompt": str(
                    prompt
                ),
                "images": images,
            },
            timeout=3600,
        )

        if not response.get(
            "ok"
        ):
            raise RuntimeError(
                "Brain Backend 视觉推理失败："
                + str(
                    response.get(
                        "error",
                        "unknown error",
                    )
                )
            )

        return str(
            response.get(
                "content",
                "",
            )
        ).strip()

    def _target_window_rect(self):
        """
        返回当前任务绑定窗口的真实屏幕坐标：
        (left, top, right, bottom)

        没有有效绑定窗口时返回 None。
        """
        if not self.runtime.desktop_task_is_active():
            return None

        with self.runtime.desktop_lock:
            hwnd = self.runtime.desktop_task.get(
                "target_hwnd"
            )

        if not hwnd:
            return None

        if not user32.IsWindow(int(hwnd)):
            return None

        rect = wintypes.RECT()

        if not user32.GetWindowRect(
            int(hwnd),
            ctypes.byref(rect),
        ):
            return None

        if (
            rect.right <= rect.left
            or rect.bottom <= rect.top
        ):
            return None

        return (
            int(rect.left),
            int(rect.top),
            int(rect.right),
            int(rect.bottom),
        )

    def _capture_scaled(
        self,
        prefix,
        prefer_target_window=True,
    ):
        """
        截图并缩放。

        GUI 任务优先只截当前授权目标窗口，
        避免 Qwen3-VL 在整个多屏桌面中找错元素。
        返回：
          path,
          original_size,
          scaled_size,
          origin_screen_x,
          origin_screen_y,
          capture_rect_screen
        """
        screenshot_dir = (
            WORKSPACE
            / "screenshots"
        )

        screenshot_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = screenshot_dir / (
            f"{prefix}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        )

        full_image = ImageGrab.grab(
            all_screens=True
        )

        virtual_left = (
            user32.GetSystemMetrics(76)
        )
        virtual_top = (
            user32.GetSystemMetrics(77)
        )

        full_width, full_height = (
            full_image.size
        )

        capture_rect = None

        if prefer_target_window:
            capture_rect = (
                self._target_window_rect()
            )

        if capture_rect is not None:
            left, top, right, bottom = (
                capture_rect
            )

            # Windows screen coordinates -> ImageGrab image coordinates
            crop_left = max(
                0,
                left - virtual_left,
            )
            crop_top = max(
                0,
                top - virtual_top,
            )
            crop_right = min(
                full_width,
                right - virtual_left,
            )
            crop_bottom = min(
                full_height,
                bottom - virtual_top,
            )

            if (
                crop_right > crop_left
                and crop_bottom > crop_top
            ):
                image = full_image.crop(
                    (
                        crop_left,
                        crop_top,
                        crop_right,
                        crop_bottom,
                    )
                )

                origin_x = (
                    virtual_left
                    + crop_left
                )
                origin_y = (
                    virtual_top
                    + crop_top
                )

                actual_rect = (
                    origin_x,
                    origin_y,
                    origin_x
                    + image.size[0],
                    origin_y
                    + image.size[1],
                )

            else:
                image = full_image
                origin_x = virtual_left
                origin_y = virtual_top
                actual_rect = (
                    virtual_left,
                    virtual_top,
                    virtual_left + full_width,
                    virtual_top + full_height,
                )

        else:
            image = full_image
            origin_x = virtual_left
            origin_y = virtual_top
            actual_rect = (
                virtual_left,
                virtual_top,
                virtual_left + full_width,
                virtual_top + full_height,
            )

        original_size = image.size

        scaled = image.copy()

        scaled.thumbnail(
            (
                VISION_MAX_IMAGE_EDGE,
                VISION_MAX_IMAGE_EDGE,
            )
        )

        scaled.save(
            path,
            format="PNG",
        )

        return (
            path,
            original_size,
            scaled.size,
            int(origin_x),
            int(origin_y),
            actual_rect,
        )

    def analyze_screen(
        self,
        question: str = "描述当前主要窗口和与任务相关的可交互元素。",
    ) -> str:
        """用本地视觉模型分析当前屏幕。"""
        ok, reason = self.permission.require("screen_read")
        if not ok:
            return reason
        path, original, scaled, _, _, capture_rect = self._capture_scaled("analysis")
        prompt = (
            "你是本地 Windows 视觉模块。只描述实际可见内容，不猜。"
            f"\n原始桌面尺寸：{original[0]}x{original[1]}"
            f"\n分析图尺寸：{scaled[0]}x{scaled[1]}"
            f"\n当前截图范围（屏幕坐标）：{capture_rect}"
            "\n如果存在当前授权目标窗口，本图只包含该窗口。"
            f"\n任务：{question}"
            "\n请简洁说明主要窗口、相关内容和明显可交互元素。"
        )

        self._prepare()
        print("[视觉] 正在分析当前屏幕……")
        try:
            result = self._remote_vision_chat(
                prompt,
                [str(path)],
            )
        finally:
            self._finish()

        self.runtime.mark_activity("analyze_screen")
        return "【当前屏幕视觉分析】\n" + (
            result or "视觉模型没有返回有效结果。"
        )

    def locate_in_image_region(
        self,
        description: str,
        image_path: str,
        screen_rect,
        min_confidence: float = 0.72,
    ) -> str:
        """
        在已经保存的局部截图中定位元素，
        并映射回真实屏幕坐标。

        专用于微信搜索结果/聊天标题等局部区域，
        避免左侧聊天列表与右侧聊天内容互相干扰。
        """
        target = str(description).strip()

        if not target:
            return "没有提供需要定位的界面元素。"

        from PIL import Image

        try:
            image = Image.open(
                str(image_path)
            ).convert("RGB")
        except Exception as e:
            return f"无法打开局部截图：{e}"

        original = image.size
        scaled_image = image.copy()

        scaled_image.thumbnail(
            (
                VISION_MAX_IMAGE_EDGE,
                VISION_MAX_IMAGE_EDGE,
            )
        )

        scaled_dir = (
            WORKSPACE
            / "screenshots"
        )

        scaled_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        scaled_path = (
            scaled_dir
            / "locator_region_scaled.png"
        )

        scaled_image.save(
            scaled_path,
            format="PNG",
        )

        prompt = (
            "你是微信 GUI 精确定位器。"
            f"\\n任务：{target}"
            f"\\n截图尺寸：{scaled_image.size[0]}x{scaled_image.size[1]}"
            "\\n只根据这张局部截图判断，不参考截图外内容。"
            "\\n必须精确匹配用户指定的文字/数字。"
            "\\n优先返回 bbox。"
            "\\n严格只返回 JSON："
            '{"found":true,"bbox":[x1,y1,x2,y2],'
            '"confidence":0到1,"reason":"短说明"}'
            "\\n如果找不到完全匹配项，found=false。"
        )

        self._prepare()

        try:
            raw = self._remote_vision_chat(
                prompt,
                [str(scaled_path)],
            )

        finally:
            self._finish()

        data = self._extract_json(raw)

        if not data or not data.get("found"):
            return (
                f"没有在局部截图中可靠找到：{target}"
            )

        point = self._resolve_locator_point(
            data,
            scaled_image.size[0],
            scaled_image.size[1],
        )

        if point is None:
            return "视觉定位失败：无法解析局部坐标。"

        ax, ay = point

        try:
            confidence = float(
                data.get("confidence", 0)
            )
        except Exception:
            confidence = 0.0

        if confidence < float(min_confidence):
            return (
                f"局部视觉定位置信度不足（{confidence:.2f}）。"
            )

        if not (
            0 <= ax < scaled_image.size[0]
            and 0 <= ay < scaled_image.size[1]
        ):
            return (
                "视觉定位失败：局部坐标超出截图范围。"
            )

        left, top, right, bottom = [
            int(v)
            for v in screen_rect
        ]

        region_width = right - left
        region_height = bottom - top

        x = left + int(
            round(
                ax
                * region_width
                / scaled_image.size[0]
            )
        )

        y = top + int(
            round(
                ay
                * region_height
                / scaled_image.size[1]
            )
        )

        if not (
            left <= x < right
            and top <= y < bottom
        ):
            return (
                "视觉定位失败：映射坐标超出局部区域。"
            )

        return json.dumps(
            {
                "found": True,
                "x": x,
                "y": y,
                "confidence": round(
                    confidence,
                    3,
                ),
                "reason": str(
                    data.get("reason", "")
                )[:160],
            },
            ensure_ascii=False,
        )

    def analyze_image_region(
        self,
        question: str,
        image_path: str,
        reference_image: str = None,
    ) -> str:
        """
        只分析一张指定局部截图。
        """
        prompt = (
            "你是微信界面验证器。"
            "\\n只根据这张局部截图回答，"
            "不要参考截图之外的聊天列表或其他区域。"
            f"\\n任务：{question}"
        )

        self._prepare()

        try:
            images = [
                str(image_path)
            ]

            if (
                reference_image
                and Path(
                    str(reference_image)
                ).exists()
            ):
                images.append(
                    str(reference_image)
                )

            return self._remote_vision_chat(
                prompt,
                images,
            )

        finally:
            self._finish()

    def locate_screen_element(self, description: str) -> str:
        """视觉定位一个 UI 元素，返回真实虚拟桌面像素坐标和置信度。"""
        ok, reason = self.permission.require("screen_read")
        if not ok:
            return reason
        target = str(description).strip()
        if not target:
            return "没有提供需要定位的界面元素。"

        (
            path,
            original,
            scaled,
            origin_x,
            origin_y,
            capture_rect,
        ) = self._capture_scaled(
            "locate",
            prefer_target_window=True,
        )

        prompt = (
            "你是 Windows GUI 元素定位器。只定位，不执行。"
            f"\n寻找：{target}"
            f"\n截图尺寸：{scaled[0]}x{scaled[1]}"
            "\n优先返回目标元素的矩形框 bbox。"
            "\n严格只返回 JSON，格式："
            '{"found":true,"bbox":[x1,y1,x2,y2],'
            '"confidence":0到1,"reason":"短说明"}'
            "\n如果只能给中心点，也可以返回："
            '{"found":true,"x":整数,"y":整数,'
            '"confidence":0到1,"reason":"短说明"}'
            "\n坐标可以是截图像素，也可以是 0~1000 归一化坐标。"
            "\n不确定就 found=false，绝对不要猜。"
        )

        self._prepare()
        try:
            raw = self._remote_vision_chat(
                prompt,
                [str(path)],
            )
        finally:
            self._finish()

        data = self._extract_json(raw)
        if not data or not data.get("found"):
            return f"没有可靠找到界面元素：{target}"

        point = self._resolve_locator_point(
            data,
            scaled[0],
            scaled[1],
        )

        if point is None:
            return "视觉定位失败：无法解析 x/y 或 bbox。"

        ax, ay = point

        try:
            confidence = float(
                data.get(
                    "confidence",
                    0,
                )
            )
        except Exception:
            confidence = 0.0

        if confidence < 0.60:
            return (
                f"视觉定位置信度不足（{confidence:.2f}），拒绝点击。"
            )

        if not (0 <= ax < scaled[0] and 0 <= ay < scaled[1]):
            return "视觉定位失败：坐标超出分析图范围。"

        # 分析图坐标 -> 当前截图原始像素 -> Windows 屏幕坐标
        x = (
            int(
                round(
                    ax
                    * original[0]
                    / scaled[0]
                )
            )
            + int(origin_x)
        )

        y = (
            int(
                round(
                    ay
                    * original[1]
                    / scaled[1]
                )
            )
            + int(origin_y)
        )

        # GUI 任务中，定位点必须仍在授权目标窗口截图范围内。
        left, top, right, bottom = (
            capture_rect
        )

        if not (
            left <= x < right
            and top <= y < bottom
        ):
            return (
                "视觉定位失败："
                "模型返回的点超出当前授权目标窗口范围。"
            )

        self.runtime.mark_activity("locate_screen_element")
        return json.dumps(
            {
                "found": True,
                "description": target,
                "x": x,
                "y": y,
                "confidence": round(confidence, 3),
                "reason": str(data.get("reason", ""))[:120],
            },
            ensure_ascii=False,
        )

    def click_screen_element(
        self,
        description: str,
        button: str = "left",
    ) -> str:
        """视觉定位 UI 元素并真实点击；需要当前任务 mouse 权限。"""
        if not self.runtime.desktop_has("mouse"):
            return "当前桌面任务没有鼠标点击权限。"
        if not self.desktop.desktop_target_ok():
            # 当前任务已经明确授权这个窗口，因此允许先尝试重新聚焦同一 HWND。
            with self.runtime.desktop_lock:
                hwnd = self.runtime.desktop_task.get(
                    "target_hwnd"
                )

            if (
                not hwnd
                or not self.desktop._force_foreground(
                    int(hwnd)
                )
            ):
                self.runtime.clear_desktop_task(
                    preserve_request=True
                )
                return (
                    "目标窗口已不在前台，"
                    "并且无法恢复到已授权窗口，任务授权已失效。"
                )

        located = self.locate_screen_element(description)
        try:
            data = json.loads(located)
        except Exception:
            return f"无法执行点击。定位结果：{located}"

        result = self.desktop.mouse_click(
            x=int(data["x"]),
            y=int(data["y"]),
            button=button,
        )
        if not result.startswith("已在"):
            return result

        return (
            f"已真实点击界面元素：{description}\n"
            f"坐标：({data['x']}, {data['y']})\n"
            f"视觉置信度：{data['confidence']}"
        )

    def capture_screen(self) -> str:
        """截取当前桌面；需要本任务 screen_read 授权。"""
        ok, reason = self.permission.require("screen_read")
        if not ok:
            return reason
        path, original, _, _, _, _ = self._capture_scaled("capture")
        self.runtime.mark_activity("capture_screen")
        return (
            f"已截取当前桌面：{path.relative_to(WORKSPACE)}；"
            f"原始尺寸：{original[0]}x{original[1]}"
        )
