import base64
import tempfile
from pathlib import Path

from ollama import chat, generate

from .config import (
    MODEL,
    REASONING_MODEL,
    VISION_MODEL,
    VISION_NUM_CTX,
)


class BackendVisionInference:
    """
    Brain Backend 视觉推理服务。

    Windows Frontend 只负责截图。
    图片通过 IPC 发送到这里，再由 qwen3-vl 推理。
    """

    @staticmethod
    def _unload(model):
        try:
            generate(
                model=model,
                prompt="",
                keep_alive=0,
            )
        except Exception:
            pass

    def infer(
        self,
        prompt,
        images_base64,
    ):
        if not isinstance(
            images_base64,
            list,
        ):
            return {
                "ok": False,
                "error": "images must be a list",
            }

        if not images_base64:
            return {
                "ok": False,
                "error": "no image supplied",
            }

        temp_paths = []

        try:
            # 视觉模型运行前释放文本模型显存。
            self._unload(MODEL)
            self._unload(REASONING_MODEL)

            for index, encoded in enumerate(
                images_base64
            ):
                try:
                    raw = base64.b64decode(
                        encoded
                    )
                except Exception:
                    return {
                        "ok": False,
                        "error": (
                            f"invalid image payload #{index}"
                        ),
                    }

                handle = tempfile.NamedTemporaryFile(
                    prefix="qingyuan_vision_",
                    suffix=".png",
                    delete=False,
                )

                handle.write(raw)
                handle.close()

                temp_paths.append(
                    Path(
                        handle.name
                    )
                )

            response = chat(
                model=VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": str(prompt),
                    "images": [
                        str(p)
                        for p in temp_paths
                    ],
                }],
                think=False,
                stream=False,
                keep_alive=0,
                options={
                    "num_ctx": VISION_NUM_CTX,
                },
            )

            content = (
                response.message.content
                .strip()
            )

            return {
                "ok": True,
                "content": content,
                "model": VISION_MODEL,
            }

        except Exception as e:
            return {
                "ok": False,
                "error": (
                    f"{type(e).__name__}: {e}"
                ),
            }

        finally:
            self._unload(
                VISION_MODEL
            )

            for path in temp_paths:
                try:
                    path.unlink(
                        missing_ok=True
                    )
                except Exception:
                    pass
