from pathlib import Path

MODEL = "qwen3:4b-instruct"
MODEL_NUM_CTX = 6144

# 复杂理解 / 规划 / 电脑任务使用的强模型。
# 如果未安装或调用失败，会自动回退 MODEL。
REASONING_MODEL = "qwen3:8b"
REASONING_MODEL_NUM_CTX = 8192
REASONING_MODEL_KEEP_ALIVE = "45s"

# 日常聊天保留 4B，降低延迟和显存占用。
CHAT_MODEL_KEEP_ALIVE = "2m"
MAX_RECENT_MESSAGES = 4

VISION_MODEL = "qwen3-vl:4b-instruct"
VISION_NUM_CTX = 4096
VISION_MAX_IMAGE_EDGE = 1280

VOICE_SPEED = 1.0

TTS_URL = "http://127.0.0.1:8765/speak"
TTS_STOP_URL = "http://127.0.0.1:8765/stop"
TTS_SHUTDOWN_URL = "http://127.0.0.1:8765/shutdown"

STT_URL = "http://127.0.0.1:8766/listen"
STT_CANCEL_URL = "http://127.0.0.1:8766/cancel"
STT_SHUTDOWN_URL = "http://127.0.0.1:8766/shutdown"

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8767

WAKE_WORD = "清渊"
WAKE_FIRST_CHARS = set("清青轻輕情请請倾傾卿")
WAKE_SECOND_CHARS = set("渊淵源原元园園愿願冤云雲员員圆圓袁缘緣援")

ACTIVE_WINDOW_SECONDS = 45.0
CONFIRM_TIMEOUT_SECONDS = 45.0
DESKTOP_TASK_IDLE_TIMEOUT_SECONDS = 120.0
DESKTOP_TASK_MAX_GUARD_LOOPS = 6

TASK_CAPABILITIES = {
    # read-only
    "screen_read",
    "window_read",
    "file_read",

    # desktop mutation
    "window_control",
    "mouse",
    "keyboard",
    "scroll",

    # process/app
    "app_launch",

    # system power/session control
    "power_control",

    # filesystem mutation
    "file_write",
    "file_move",
    "file_delete",
}

# 兼容旧模块名
DESKTOP_CAPABILITIES = TASK_CAPABILITIES

PERSISTENT_SCREEN_ACCESS = True

WORKSPACE = Path(r"C:\MyAgent\workspace").resolve()
DATA_DIR = Path(r"C:\MyAgent\data").resolve()
MEMORY_FILE = DATA_DIR / "memory.json"
ERROR_LOG_FILE = DATA_DIR / "agent_error.log"

ALLOWED_APPS = {
    "记事本": "notepad.exe",
    "notepad": "notepad.exe",
    "计算器": "calc.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "资源管理器": "explorer.exe",
    "文件资源管理器": "explorer.exe",
    "explorer": "explorer.exe",
}


# ============================================================
# 视觉截图存储策略
# ============================================================

# 普通临时截图目录：
# C:\MyAgent\workspace\screenshots\
TEMP_SCREENSHOT_RETENTION_MINUTES = 30

# 微信成功经验库：
# C:\MyAgent\workspace\wechat_debug\<category>\
# 每个分类最多保留最近 N 张高价值样本。
WECHAT_EXPERIENCE_MAX_PER_CATEGORY = 12

SCREENSHOT_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}
