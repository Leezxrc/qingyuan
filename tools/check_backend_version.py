from qingyuan.ipc_config import (
    BACKEND_URL,
)
from qingyuan.ipc_http import (
    get_json,
)
from qingyuan.version import (
    BACKEND_PROTOCOL_VERSION,
    QINGYUAN_VERSION,
)


status = get_json(
    BACKEND_URL + "/health",
    timeout=3,
)

print("Frontend expected:")
print(
    " version =",
    QINGYUAN_VERSION,
)
print(
    " protocol =",
    BACKEND_PROTOCOL_VERSION,
)

print()
print("Backend actual:")
print(status)
