import json
import urllib.error
import urllib.request

from .ipc_auth import get_ipc_token


def post_json(
    url,
    payload,
    timeout=3600,
):
    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": (
                "application/json; charset=utf-8"
            ),
            "X-Qingyuan-Token": (
                get_ipc_token()
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read()

        return json.loads(
            raw.decode("utf-8")
        )

    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode(
                "utf-8"
            )

            return json.loads(raw)
        except Exception:
            return {
                "ok": False,
                "error": (
                    f"HTTP {e.code}: {e}"
                ),
            }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }


def get_json(
    url,
    timeout=3,
):
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "X-Qingyuan-Token": (
                get_ipc_token()
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read()

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
