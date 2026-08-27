import json
import socket
import threading
import time
from urllib.request import urlopen

import pystray
from PIL import Image, ImageDraw


AGENT_URL = "http://127.0.0.1:8767"
SINGLE_INSTANCE_HOST = "127.0.0.1"
SINGLE_INSTANCE_PORT = 8768

poll_stop = threading.Event()
latest_status = {
    "ok": False,
}

instance_socket = None


def acquire_single_instance() -> bool:

    global instance_socket

    try:

        instance_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        instance_socket.bind(
            (
                SINGLE_INSTANCE_HOST,
                SINGLE_INSTANCE_PORT,
            )
        )

        instance_socket.listen(1)

        return True

    except OSError:

        return False


def request_agent(
    path: str,
    timeout: float = 2.0,
):

    try:

        with urlopen(
            AGENT_URL + path,
            timeout=timeout,
        ) as response:

            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except Exception:

        return None


def create_icon_image(
    state: str
):

    size = 64

    image = Image.new(
        "RGBA",
        (size, size),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        image
    )

    # 不依赖外部图片文件，先用简洁的圆形状态图标。
    if state == "speaking":
        fill = (116, 181, 255, 255)

    elif state == "active":
        fill = (147, 220, 166, 255)

    elif state == "mic_off":
        fill = (145, 145, 155, 255)

    elif state == "offline":
        fill = (220, 110, 110, 255)

    else:
        fill = (174, 160, 220, 255)

    draw.ellipse(
        (6, 6, 58, 58),
        fill=fill,
    )

    draw.ellipse(
        (19, 16, 45, 42),
        outline=(255, 255, 255, 235),
        width=3,
    )

    draw.arc(
        (16, 24, 48, 53),
        start=25,
        end=155,
        fill=(255, 255, 255, 235),
        width=3,
    )

    return image


def status_state(
    status: dict
) -> str:

    if not status.get("ok"):
        return "offline"

    if not status.get(
        "mic_enabled",
        False,
    ):
        return "mic_off"

    if status.get(
        "speaking",
        False,
    ):
        return "speaking"

    if status.get(
        "conversation_active",
        False,
    ):
        return "active"

    return "standby"


def status_text(
    status: dict
) -> str:

    if not status.get("ok"):
        return "状态：清渊未连接"

    if not status.get(
        "mic_enabled",
        False,
    ):
        return "状态：麦克风已暂停"

    if status.get(
        "speaking",
        False,
    ):
        return "状态：正在说话"

    if status.get(
        "busy",
        False,
    ):
        return "状态：正在处理"

    if status.get(
        "conversation_active",
        False,
    ):

        remaining = status.get(
            "active_remaining",
            0,
        )

        return (
            f"状态：连续对话 "
            f"({remaining:.0f}s)"
        )

    return "状态：待机，等待“清渊”"


def mic_menu_text(item):

    if latest_status.get(
        "mic_enabled",
        False,
    ):
        return "暂停麦克风"

    return "恢复麦克风"


def do_toggle_mic(
    icon,
    item,
):

    if latest_status.get(
        "mic_enabled",
        False,
    ):

        request_agent(
            "/mic/off"
        )

    else:

        request_agent(
            "/mic/on"
        )


def do_standby(
    icon,
    item,
):

    request_agent(
        "/standby"
    )


def do_stop_speaking(
    icon,
    item,
):

    request_agent(
        "/stop"
    )


def do_exit(
    icon,
    item,
):

    poll_stop.set()

    request_agent(
        "/quit"
    )

    icon.stop()


def poll_status(
    icon,
):

    global latest_status

    previous_state = None
    previous_title = None

    while not poll_stop.is_set():

        status = request_agent(
            "/status",
            timeout=1.5,
        )

        if status is None:

            latest_status = {
                "ok": False,
            }

        else:

            latest_status = status


        state = status_state(
            latest_status
        )

        title = (
            "清渊 · "
            + status_text(
                latest_status
            ).replace(
                "状态：",
                ""
            )
        )


        if state != previous_state:

            icon.icon = (
                create_icon_image(
                    state
                )
            )

            previous_state = state


        if title != previous_title:

            icon.title = title

            previous_title = title


        try:
            icon.update_menu()
        except Exception:
            pass


        time.sleep(0.8)


def main():

    if not acquire_single_instance():
        return


    menu = pystray.Menu(

        pystray.MenuItem(
            lambda item:
                status_text(
                    latest_status
                ),
            None,
            enabled=False,
        ),

        pystray.Menu.SEPARATOR,

        pystray.MenuItem(
            mic_menu_text,
            do_toggle_mic,
        ),

        pystray.MenuItem(
            "进入待机",
            do_standby,
        ),

        pystray.MenuItem(
            "停止当前说话",
            do_stop_speaking,
        ),

        pystray.Menu.SEPARATOR,

        pystray.MenuItem(
            "退出清渊",
            do_exit,
        ),
    )


    icon = pystray.Icon(
        "qingyuan",
        create_icon_image(
            "offline"
        ),
        "清渊",
        menu,
    )


    polling_thread = threading.Thread(
        target=poll_status,
        args=(icon,),
        daemon=True,
    )

    polling_thread.start()

    icon.run()


if __name__ == "__main__":
    main()
