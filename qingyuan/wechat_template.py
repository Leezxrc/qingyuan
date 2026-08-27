"""
兼容旧微信代码的薄封装。

v4.15 起真正的数据源已经统一为：
C:\\MyAgent\\assets\\visual\\apps\\wechat\\
"""

from .visual_profile import (
    VisualAppProfile,
    migrate_legacy_wechat_assets,
)


class WeChatTemplate:
    def __init__(self):
        self.profile = (
            migrate_legacy_wechat_assets()
        )

    def region(
        self,
        name,
    ):
        return self.profile.region(
            name
        )

    def reference_exists(self):
        return bool(
            self.profile
            .best_reference_image()
        )

    def reference_image(self):
        return (
            self.profile
            .best_reference_image()
        )
