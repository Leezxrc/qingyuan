import secrets

from .ipc_config import (
    IPC_TOKEN_FILE,
)


def get_ipc_token():
    IPC_TOKEN_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        token = (
            IPC_TOKEN_FILE
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )

        if len(token) >= 32:
            return token

    except Exception:
        pass

    token = secrets.token_hex(
        32
    )

    IPC_TOKEN_FILE.write_text(
        token,
        encoding="utf-8",
    )

    return token
