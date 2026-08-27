import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import CONTROL_HOST, CONTROL_PORT


def start_control_server(runtime, voice):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, code, data):
            payload = json.dumps(
                data, ensure_ascii=False
            ).encode("utf-8")
            self.send_response(code)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def status(self):
            last_reply, last_reply_time = (
                runtime.get_last_assistant_text()
                if hasattr(runtime, "get_last_assistant_text")
                else ("", 0.0)
            )

            try:
                import time
                reply_age = (
                    max(0.0, time.monotonic() - last_reply_time)
                    if last_reply_time
                    else None
                )
            except Exception:
                reply_age = None

            return {
                "ok": True,
                "name": "清渊",
                "mic_enabled": bool(runtime.voice_listen_enabled),
                "conversation_active": bool(
                    runtime.is_conversation_active()
                ),
                "active_remaining": round(
                    runtime.active_remaining(), 1
                ),
                "speaking": bool(runtime.tts_speaking.is_set()),
                "busy": bool(runtime.agent_busy.is_set()),
                "confirming": bool(runtime.confirm_active.is_set()),
                "desktop_active": bool(runtime.desktop_task_is_active()),
                "last_reply": last_reply,
                "last_reply_age": (
                    round(reply_age, 1)
                    if reply_age is not None
                    else None
                ),
            }

        def do_GET(self):
            path = self.path.split("?", 1)[0]

            if path in ["/health", "/status"]:
                self.send_json(200, self.status())
                return

            if path == "/mic/on":
                runtime.voice_listen_enabled = True
                self.send_json(200, self.status())
                return

            if path == "/mic/off":
                runtime.voice_listen_enabled = False
                voice.cancel_listen()
                runtime.go_standby()
                self.send_json(200, self.status())
                return

            if path == "/standby":
                voice.stop_speaking()
                runtime.go_standby()
                self.send_json(200, self.status())
                return

            if path == "/wake":
                # 点击桌宠后，下一轮语音无需再次说唤醒词。
                runtime.voice_listen_enabled = True
                voice.cancel_listen()
                runtime.activate_conversation()
                self.send_json(200, self.status())
                return

            if path == "/stop":
                voice.stop_speaking()
                self.send_json(200, self.status())
                return

            if path == "/quit":
                voice.stop_speaking()
                voice.cancel_listen()
                runtime.stop_event.set()
                self.send_json(
                    200,
                    {"ok": True, "quitting": True},
                )
                return

            self.send_json(
                404,
                {"ok": False, "error": "Not found"},
            )

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(
        (CONTROL_HOST, CONTROL_PORT),
        Handler,
    )
    server.timeout = 0.5

    print(
        f"本地控制接口：http://{CONTROL_HOST}:{CONTROL_PORT}"
    )

    try:
        while not runtime.stop_event.is_set():
            server.handle_request()
    finally:
        server.server_close()
