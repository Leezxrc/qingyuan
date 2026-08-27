import json
import shutil
from pathlib import Path


ASSETS_DIR = Path(
    r"C:\MyAgent\assets"
)

VISUAL_DIR = (
    ASSETS_DIR
    / "visual"
)

APPS_DIR = (
    VISUAL_DIR
    / "apps"
)

LEGACY_WECHAT_DIR = (
    ASSETS_DIR
    / "wechat"
)


DEFAULT_WECHAT_LAYOUT = {
    "version": 1,
    "coordinate_system": "relative_to_window",
    "regions": {
        "search_box": {
            "box": [
                0.065,
                0.045,
                0.245,
                0.105,
            ],
            "description": "微信左上方搜索框",
        },
        "search_results": {
            "box": [
                0.055,
                0.10,
                0.29,
                0.72,
            ],
            "description": "微信左侧搜索结果区域",
        },
        "chat_header": {
            "box": [
                0.29,
                0.00,
                0.98,
                0.13,
            ],
            "description": "微信右侧当前聊天标题区域",
        },
        "message_box": {
            "box": [
                0.29,
                0.74,
                0.98,
                0.985,
            ],
            "description": "微信右侧底部消息输入区域",
        },
    },
}


class VisualAppProfile:
    """
    统一软件视觉 Profile。

    每个软件统一放：
    C:\\MyAgent\\assets\\visual\\apps\\<app_key>\\

    profile.json
        稳定 UI 区域定义

    originals\\
        用户提供的完整参考截图

    examples\\
        自动裁剪后的参考区域

    metadata\\
        截图分析元数据
    """

    def __init__(
        self,
        app_key,
    ):
        self.app_key = (
            str(app_key)
            .strip()
            .lower()
        )

        self.app_dir = (
            APPS_DIR
            / self.app_key
        )

        self.profile_path = (
            self.app_dir
            / "profile.json"
        )

        self.originals_dir = (
            self.app_dir
            / "originals"
        )

        self.examples_dir = (
            self.app_dir
            / "examples"
        )

        self.metadata_dir = (
            self.app_dir
            / "metadata"
        )

        self._ensure()

    def _ensure(self):
        self.app_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.originals_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.examples_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.metadata_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(self):
        try:
            data = json.loads(
                self.profile_path.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(data, dict):
                return data

        except Exception:
            pass

        if self.app_key == "wechat":
            return DEFAULT_WECHAT_LAYOUT

        return {
            "version": 1,
            "coordinate_system": (
                "relative_to_window"
            ),
            "regions": {},
        }

    def save(
        self,
        data,
    ):
        self._ensure()

        self.profile_path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def region(
        self,
        name,
    ):
        data = self.load()

        try:
            box = (
                data["regions"][name]["box"]
            )

            if (
                isinstance(box, list)
                and len(box) == 4
            ):
                return tuple(
                    float(v)
                    for v in box
                )
        except Exception:
            pass

        if self.app_key == "wechat":
            try:
                box = (
                    DEFAULT_WECHAT_LAYOUT
                    ["regions"]
                    [name]
                    ["box"]
                )

                return tuple(
                    float(v)
                    for v in box
                )
            except Exception:
                pass

        return None

    def best_reference_image(
        self,
    ):
        """
        优先取 originals 中最新完整参考图。
        """
        images = []

        for ext in (
            "*.png",
            "*.jpg",
            "*.jpeg",
            "*.webp",
        ):
            images.extend(
                self.originals_dir.glob(
                    ext
                )
            )

        if not images:
            return None

        images.sort(
            key=lambda p: (
                p.stat().st_mtime
            ),
            reverse=True,
        )

        return str(
            images[0]
        )


def migrate_legacy_wechat_assets():
    """
    一次性迁移旧：
    C:\\MyAgent\\assets\\wechat

    到：
    C:\\MyAgent\\assets\\visual\\apps\\wechat

    不主动删除旧目录。
    用户确认新系统正常后可手动整个删除。
    """
    profile = VisualAppProfile(
        "wechat"
    )

    migrated = []

    # ----------------------------------------
    # layout.json -> profile.json
    # ----------------------------------------

    legacy_layout = (
        LEGACY_WECHAT_DIR
        / "layout.json"
    )

    if (
        legacy_layout.exists()
        and not profile.profile_path.exists()
    ):
        try:
            data = json.loads(
                legacy_layout.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(data, dict):
                profile.save(data)
                migrated.append(
                    "layout.json -> profile.json"
                )

        except Exception:
            pass

    # 若没有任何旧 layout，也保证新 profile 存在
    if not profile.profile_path.exists():
        profile.save(
            DEFAULT_WECHAT_LAYOUT
        )

    # ----------------------------------------
    # reference_main.png -> originals
    # ----------------------------------------

    legacy_reference = (
        LEGACY_WECHAT_DIR
        / "reference_main.png"
    )

    if legacy_reference.exists():
        target = (
            profile.originals_dir
            / "reference_main.png"
        )

        if not target.exists():
            try:
                shutil.copy2(
                    legacy_reference,
                    target,
                )

                migrated.append(
                    "reference_main.png -> originals"
                )
            except Exception:
                pass

    # ----------------------------------------
    # user_examples -> examples
    # ----------------------------------------

    legacy_examples = (
        LEGACY_WECHAT_DIR
        / "user_examples"
    )

    if legacy_examples.exists():
        for source in (
            legacy_examples.rglob("*")
        ):
            if not source.is_file():
                continue

            if source.suffix.lower() not in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }:
                continue

            relative = source.relative_to(
                legacy_examples
            )

            target = (
                profile.examples_dir
                / relative
            )

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            if not target.exists():
                try:
                    shutil.copy2(
                        source,
                        target,
                    )

                    migrated.append(
                        f"user_examples/{relative}"
                    )
                except Exception:
                    pass

    if migrated:
        print(
            "\\n[视觉资料迁移] 微信旧资料已迁移："
        )

        for item in migrated:
            print(
                f"[视觉资料迁移] {item}"
            )

    return profile
