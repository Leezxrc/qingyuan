import sys
from pathlib import Path

ROOT = Path(r"C:\MyAgent")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qingyuan.version import QINGYUAN_VERSION, BACKEND_PROTOCOL_VERSION

assert QINGYUAN_VERSION == "5.8.4", QINGYUAN_VERSION
assert BACKEND_PROTOCOL_VERSION == 7, BACKEND_PROTOCOL_VERSION

# Import the two modules that depend on the protocol constant.
import qingyuan.frontend_service
import qingyuan.backend_service

print("[OK] QINGYUAN_VERSION:", QINGYUAN_VERSION)
print("[OK] BACKEND_PROTOCOL_VERSION:", BACKEND_PROTOCOL_VERSION)
print("[OK] frontend_service import")
print("[OK] backend_service import")
print("ALL_TESTS_OK")
