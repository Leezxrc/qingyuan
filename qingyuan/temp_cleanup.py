import threading
import time

from .config import (
    WORKSPACE,
    TEMP_SCREENSHOT_RETENTION_MINUTES,
    SCREENSHOT_EXTENSIONS,
)


class TempCleanupService:
    """
    只清理：
    C:\\MyAgent\\workspace\\screenshots\\

    不碰：
    - assets\\wechat
    - workspace\\wechat_debug
    """

    def __init__(
        self,
        stop_event,
    ):
        self.stop_event = stop_event

    def cleanup_once(self):
        temp_dir = (
            WORKSPACE
            / "screenshots"
        )

        if not temp_dir.exists():
            return 0

        cutoff = (
            time.time()
            - TEMP_SCREENSHOT_RETENTION_MINUTES
            * 60
        )

        deleted = 0

        for path in temp_dir.rglob("*"):

            if not path.is_file():
                continue

            if (
                path.suffix.lower()
                not in SCREENSHOT_EXTENSIONS
            ):
                continue

            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    deleted += 1
            except Exception:
                continue

        if deleted:
            print(
                f"\\n[临时文件] 自动清理 {deleted} 张过期截图"
            )

        return deleted

    def run(self):
        self.cleanup_once()

        while not self.stop_event.wait(
            300
        ):
            self.cleanup_once()

    def start(self):
        thread = threading.Thread(
            target=self.run,
            name="qingyuan-temp-cleanup",
            daemon=True,
        )

        thread.start()

        return thread
