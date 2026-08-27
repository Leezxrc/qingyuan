import hashlib
import shutil
from pathlib import Path

from PIL import Image

from .config import (
    WORKSPACE,
    WECHAT_EXPERIENCE_MAX_PER_CATEGORY,
)


class WeChatExperienceLibrary:
    """
    微信视觉经验库。

    assets\\wechat
        = 用户主动提供的长期参考资料

    workspace\\wechat_debug
        = 清渊自己执行成功后留下的高价值经验

    workspace\\screenshots
        = 临时工作截图，自动过期
    """

    CATEGORIES = {
        "search_box",
        "search_result",
        "chat_header",
        "message_box",
        "send_success",
        "failures",
    }

    def __init__(self):
        self.base_dir = (
            WORKSPACE
            / "wechat_debug"
        )

        self.temp_dir = (
            WORKSPACE
            / "screenshots"
        )

        self.base_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.temp_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        for category in self.CATEGORIES:
            (
                self.base_dir
                / category
            ).mkdir(
                parents=True,
                exist_ok=True,
            )

    @staticmethod
    def _perceptual_signature(
        image_path,
    ):
        """
        轻量重复检测：
        缩成 16x16 灰度图后做哈希。
        """
        try:
            with Image.open(
                image_path
            ) as image:
                small = (
                    image.convert("L")
                    .resize((16, 16))
                )

                payload = bytes(
                    small.getdata()
                )

            return hashlib.sha1(
                payload
            ).hexdigest()

        except Exception:
            return None

    def _is_duplicate(
        self,
        category_dir,
        source_path,
    ):
        source_sig = (
            self._perceptual_signature(
                source_path
            )
        )

        if not source_sig:
            return False

        for existing in (
            category_dir
            .glob("*.png")
        ):
            existing_sig = (
                self._perceptual_signature(
                    existing
                )
            )

            if (
                existing_sig
                and existing_sig
                == source_sig
            ):
                return True

        return False

    def _trim_category(
        self,
        category_dir,
    ):
        files = sorted(
            [
                p
                for p in category_dir.iterdir()
                if p.is_file()
                and p.suffix.lower()
                in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                }
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old in files[
            WECHAT_EXPERIENCE_MAX_PER_CATEGORY:
        ]:
            try:
                old.unlink()
            except Exception:
                pass

    def promote(
        self,
        source_path,
        category,
        label=None,
    ):
        """
        把成功任务中的高价值截图提升为长期经验。

        同类重复截图不会重复保存。
        每类只保留最近 N 张。
        """
        if category not in self.CATEGORIES:
            return None

        source = Path(
            source_path
        )

        if not source.exists():
            return None

        category_dir = (
            self.base_dir
            / category
        )

        category_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if self._is_duplicate(
            category_dir,
            source,
        ):
            return None

        safe_label = (
            str(label or category)
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

        destination = (
            category_dir
            / f"{int(source.stat().st_mtime * 1000)}_{safe_label}.png"
        )

        try:
            shutil.copy2(
                source,
                destination,
            )

            self._trim_category(
                category_dir
            )

            print(
                f"\\n[经验库] 已保存：{destination}"
            )

            return str(destination)

        except Exception:
            return None
