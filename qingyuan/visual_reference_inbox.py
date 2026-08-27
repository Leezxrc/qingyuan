import json
import re
import shutil
import threading
import time
from pathlib import Path

from PIL import Image
from ollama import chat

from .config import (
    VISION_MODEL,
    VISION_NUM_CTX,
)
from .visual_profile import VisualAppProfile


BASE_DIR = Path(
    r"C:\MyAgent\assets\visual"
)

INBOX_DIR = (
    BASE_DIR
    / "inbox"
)

APPS_DIR = (
    BASE_DIR
    / "apps"
)

STATE_FILE = (
    BASE_DIR
    / "inbox_state.json"
)

SUPPORTED = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


COMMON_REGIONS = {
    "search_box",
    "sidebar",
    "list_area",
    "header",
    "main_content",
    "input_box",
    "toolbar",
    "navigation",
}


class VisualReferenceInbox:
    """
    通用软件截图收件箱。

    用户只需把完整软件截图丢进：
        C:\\MyAgent\\assets\\visual\\inbox\\

    清渊自动：
    1. 判断是什么软件
    2. 识别主要 UI 区域
    3. 永久归档原始截图
    4. 保存 region metadata
    5. 裁剪有用 UI 区域
    6. 按软件分类

    不执行任何电脑操作，不申请 Task Permit。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._ensure_dirs()

    def _ensure_dirs(self):
        INBOX_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        APPS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _safe_name(value):
        value = str(value).strip().lower()

        aliases = {
            "wechat": "wechat",
            "微信": "wechat",
            "chrome": "chrome",
            "google chrome": "chrome",
            "谷歌浏览器": "chrome",
            "file explorer": "file_explorer",
            "windows explorer": "file_explorer",
            "资源管理器": "file_explorer",
            "文件资源管理器": "file_explorer",
            "edge": "edge",
            "microsoft edge": "edge",
            "discord": "discord",
            "steam": "steam",
            "notepad": "notepad",
            "记事本": "notepad",
        }

        if value in aliases:
            return aliases[value]

        cleaned = re.sub(
            r"[^a-z0-9_\-]+",
            "_",
            value,
        ).strip("_")

        return cleaned or "unknown_app"

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
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @staticmethod
    def _fingerprint(path):
        stat = path.stat()

        return (
            f"{stat.st_size}:"
            f"{int(stat.st_mtime_ns)}"
        )

    def _load_state(self):
        try:
            data = json.loads(
                STATE_FILE.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(data, dict):
                return data

        except Exception:
            pass

        return {
            "processed": {}
        }

    def _save_state(self, state):
        try:
            STATE_FILE.write_text(
                json.dumps(
                    state,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _analyze_screenshot(
        self,
        source,
    ):
        prompt = """
你是桌面软件 UI 截图分析器。

请分析这张完整软件窗口截图。

任务：
1. 判断最可能是什么软件。
2. 给出软件的稳定短名称。
3. 找出对以后自动操作最有价值的 UI 区域。
4. 所有 bbox 使用 0~1000 归一化坐标。
5. 不确定的区域不要猜。
6. 只返回 JSON。

允许的通用 region 名称优先使用：
search_box
sidebar
list_area
header
main_content
input_box
toolbar
navigation

如果软件有明显特殊区域，也可以自定义名称。

严格格式：
{
  "app_name": "软件显示名称",
  "app_key": "英文或拼音短名",
  "confidence": 0.0,
  "regions": [
    {
      "name": "search_box",
      "bbox": [x1,y1,x2,y2],
      "confidence": 0.0,
      "description": "简短说明"
    }
  ]
}
""".strip()

        try:
            response = chat(
                model=VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [str(source)],
                }],
                think=False,
                keep_alive=0,
                options={
                    "num_ctx": VISION_NUM_CTX,
                },
            )

            data = self._extract_json(
                response.message.content
            )

            if isinstance(data, dict):
                return data

        except Exception as e:
            print(
                f"\n[视觉参考库] 分析失败：{e}"
            )

        return {
            "app_name": "Unknown",
            "app_key": "unknown_app",
            "confidence": 0.0,
            "regions": [],
        }

    @staticmethod
    def _crop_normalized(
        image,
        bbox,
    ):
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
        ):
            return None

        try:
            x1, y1, x2, y2 = [
                float(v)
                for v in bbox
            ]
        except Exception:
            return None

        width, height = image.size

        left = int(
            max(0, min(1000, x1))
            / 1000.0
            * width
        )

        top = int(
            max(0, min(1000, y1))
            / 1000.0
            * height
        )

        right = int(
            max(0, min(1000, x2))
            / 1000.0
            * width
        )

        bottom = int(
            max(0, min(1000, y2))
            / 1000.0
            * height
        )

        if (
            right <= left
            or bottom <= top
        ):
            return None

        return image.crop(
            (
                left,
                top,
                right,
                bottom,
            )
        )

    def process_file(
        self,
        path,
    ):
        source = Path(path)

        if (
            not source.exists()
            or source.suffix.lower()
            not in SUPPORTED
        ):
            return False

        state = self._load_state()

        fingerprint = self._fingerprint(
            source
        )

        old = (
            state
            .get("processed", {})
            .get(source.name)
        )

        if (
            isinstance(old, dict)
            and old.get("fingerprint")
            == fingerprint
        ):
            return False

        analysis = self._analyze_screenshot(
            source
        )

        app_name = str(
            analysis.get(
                "app_name",
                "Unknown",
            )
        ).strip()

        app_key = self._safe_name(
            analysis.get(
                "app_key",
                app_name,
            )
        )

        visual_profile = VisualAppProfile(
            app_key
        )

        app_dir = (
            visual_profile.app_dir
        )

        originals = (
            visual_profile.originals_dir
        )

        examples = (
            visual_profile.examples_dir
        )

        metadata_dir = (
            visual_profile.metadata_dir
        )

        originals.mkdir(
            parents=True,
            exist_ok=True,
        )

        examples.mkdir(
            parents=True,
            exist_ok=True,
        )

        metadata_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        archive_target = (
            originals
            / source.name
        )

        if (
            source.resolve()
            != archive_target.resolve()
        ):
            shutil.copy2(
                source,
                archive_target,
            )

        saved_regions = {}

        try:
            with Image.open(source) as img:
                image = img.convert("RGB")

                regions = analysis.get(
                    "regions",
                    [],
                )

                if isinstance(
                    regions,
                    list,
                ):
                    for region in regions:
                        if not isinstance(
                            region,
                            dict,
                        ):
                            continue

                        try:
                            confidence = float(
                                region.get(
                                    "confidence",
                                    0,
                                )
                            )
                        except Exception:
                            confidence = 0.0

                        if confidence < 0.70:
                            continue

                        region_name = (
                            self._safe_name(
                                region.get(
                                    "name",
                                    "region",
                                )
                            )
                        )

                        cropped = (
                            self._crop_normalized(
                                image,
                                region.get(
                                    "bbox"
                                ),
                            )
                        )

                        if cropped is None:
                            continue

                        category_dir = (
                            examples
                            / region_name
                        )

                        category_dir.mkdir(
                            parents=True,
                            exist_ok=True,
                        )

                        out = (
                            category_dir
                            / f"{source.stem}_{region_name}.png"
                        )

                        cropped.save(
                            out,
                            format="PNG",
                        )

                        saved_regions[
                            region_name
                        ] = str(out)

        except Exception as e:
            print(
                f"\n[视觉参考库] 裁剪失败：{e}"
            )

        metadata = {
            "source": str(source),
            "archive": str(
                archive_target
            ),
            "app_name": app_name,
            "app_key": app_key,
            "confidence": analysis.get(
                "confidence",
                0,
            ),
            "regions": analysis.get(
                "regions",
                [],
            ),
            "saved_regions": saved_regions,
            "processed_at": time.time(),
        }

        metadata_path = (
            metadata_dir
            / f"{source.stem}.json"
        )

        metadata_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        state.setdefault(
            "processed",
            {},
        )[source.name] = {
            "fingerprint": fingerprint,
            "app_key": app_key,
            "metadata": str(
                metadata_path
            ),
        }

        self._save_state(
            state
        )

        print(
            f"\n[视觉参考库] 已学习：{source.name}"
        )

        print(
            f"[视觉参考库] 软件：{app_name} ({app_key})"
        )

        if saved_regions:
            print(
                "[视觉参考库] 已自动分类："
                + "、".join(
                    saved_regions.keys()
                )
            )

        return True

    def scan_once(self):
        self._ensure_dirs()

        count = 0

        with self._lock:
            for path in sorted(
                INBOX_DIR.iterdir()
            ):
                if (
                    path.is_file()
                    and path.suffix.lower()
                    in SUPPORTED
                ):
                    if self.process_file(
                        path
                    ):
                        count += 1

        return count

    def run(
        self,
        stop_event,
    ):
        self.scan_once()

        while not stop_event.wait(
            30
        ):
            self.scan_once()

    def start(
        self,
        stop_event,
    ):
        thread = threading.Thread(
            target=self.run,
            args=(stop_event,),
            name="qingyuan-visual-reference-inbox",
            daemon=True,
        )

        thread.start()

        return thread
