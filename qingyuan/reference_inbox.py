"""
兼容旧版模块。

v4.14 起统一使用：
VisualReferenceInbox
"""

from .visual_reference_inbox import (
    VisualReferenceInbox,
)

WeChatReferenceInbox = (
    VisualReferenceInbox
)
