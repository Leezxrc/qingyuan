# Qingyuan Voice Core 3.0 compatibility entry.
# Existing launcher still starts this filename on port 8766.
from pathlib import Path
import runpy

TARGET = Path(__file__).with_name("qingyuan_voice_core.py")
runpy.run_path(str(TARGET), run_name="__main__")
