import os
from pathlib import Path


DATA_DIR = Path(
    r"C:\MyAgent\data"
)

BACKEND_HOST = os.environ.get(
    "QINGYUAN_BACKEND_HOST",
    "127.0.0.1",
)

BACKEND_PORT = int(
    os.environ.get(
        "QINGYUAN_BACKEND_PORT",
        "8770",
    )
)

BACKEND_URL = os.environ.get(
    "QINGYUAN_BACKEND_URL",
    f"http://{BACKEND_HOST}:{BACKEND_PORT}",
)

ACTION_HOST = os.environ.get(
    "QINGYUAN_ACTION_HOST",
    "127.0.0.1",
)

ACTION_PORT = int(
    os.environ.get(
        "QINGYUAN_ACTION_PORT",
        "8771",
    )
)

ACTION_URL = os.environ.get(
    "QINGYUAN_ACTION_URL",
    f"http://{ACTION_HOST}:{ACTION_PORT}",
)

IPC_TOKEN_FILE = (
    DATA_DIR
    / "ipc_token.txt"
)

# 当前默认同机部署。
# 以后把 Brain Backend 放到另一台机器时：
# - 前端 ACTION_HOST 需要手动改为可访问地址
# - 防火墙只允许后端机器
# - 必须继续使用 IPC token
AUTO_START_LOCAL_BACKEND = (
    os.environ.get(
        "QINGYUAN_AUTO_START_BACKEND",
        "1",
    )
    != "0"
)

AUTO_SHUTDOWN_LOCAL_BACKEND = (
    os.environ.get(
        "QINGYUAN_AUTO_SHUTDOWN_BACKEND",
        "1",
    )
    != "0"
)
