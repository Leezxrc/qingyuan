import sys


def _configure_utf8_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(
                    encoding="utf-8",
                    errors="replace",
                )
        except Exception:
            pass


_configure_utf8_stdio()

from qingyuan.frontend_service import run


if __name__ == "__main__":
    run()
