import contextlib
import io
import json
import queue
import threading
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from .agent_core import AgentCore
from .backend_vision import BackendVisionInference
from .backend_bridge import (
    RemoteToolFactory,
    RemoteVoiceProxy,
)
from .cognitive_router import (
    CognitiveRouter,
)
from .config import (
    MAX_RECENT_MESSAGES,
    MODEL_NUM_CTX,
)
from .context_manager import (
    ConversationContextManager,
)
from .critic import PlanCritic
from .ipc_auth import get_ipc_token
from .ipc_config import (
    BACKEND_HOST,
    BACKEND_PORT,
)
from .knowledge_memory import (
    KnowledgeMemory,
)
from .local_rag import (
    LocalDocumentRAG,
)
from .memory import MemoryStore
from .model_router import ModelRouter
from .planner import Planner
from .replanner import Replanner
from .router import IntentRouter
from .runtime import RuntimeState
from .teach_classifier import TeachExecuteClassifier
from .semantic_interpreter import (
    SemanticInterpreter,
)
from .skills import SkillLibrary
from .skill_learning import SkillLearningManager
from .verifier import Verifier
from .version import (
    BACKEND_PROTOCOL_VERSION,
    QINGYUAN_VERSION,
)


class BrainBackend:
    """
    清渊 Brain Backend。

    不直接拥有 Windows 鼠标/键盘权限。
    真实动作通过 Action Host 代理。
    """

    def __init__(self):
        self.runtime = RuntimeState()

        self.model_router = (
            ModelRouter()
        )

        self.backend_vision = (
            BackendVisionInference()
        )

        self.voice = (
            RemoteVoiceProxy(
                self.runtime
            )
        )

        self.knowledge = (
            KnowledgeMemory(
                self.model_router
            )
        )

        self.teach_classifier = (
            TeachExecuteClassifier()
        )

        self.memory = MemoryStore(
            self.runtime,
            self.voice,
            knowledge=self.knowledge,
        )

        self.router = IntentRouter()

        self.planner = Planner(
            self.model_router
        )

        self.verifier = Verifier(
            self.runtime
        )

        self.replanner = Replanner()

        self.semantic_interpreter = (
            SemanticInterpreter(
                self.model_router
            )
        )

        self.cognitive_router = (
            CognitiveRouter()
        )

        self.context_manager = (
            ConversationContextManager(
                self.model_router
            )
        )

        self.critic = PlanCritic(
            self.model_router
        )

        self.local_rag = (
            LocalDocumentRAG()
        )

        self.local_rag.start_watcher(
            self.runtime.stop_event,
            interval_seconds=60,
        )

        self.skill_library = (
            SkillLibrary()
        )

        self.skill_learning = (
            SkillLearningManager(
                self.model_router,
                min_successes=2,
            )
        )

        self.tool_factory = (
            RemoteToolFactory(
                self.runtime,
                self.memory,
            )
        )

        self.core = AgentCore(
            self.runtime,
            self.voice,
            self.memory,
            self.router,
            self.tool_factory,
            self.planner,
            self.verifier,
            self.replanner,
            self.model_router,
            self.cognitive_router,
            self.context_manager,
            self.critic,
            self.local_rag,
            self.skill_library,
            self.skill_learning,
        )

        self.command_lock = (
            threading.Lock()
        )

    def recent_semantic_context(
        self,
    ):
        items = []

        for message in (
            self.core.messages[-4:]
        ):
            if not isinstance(
                message,
                dict,
            ):
                continue

            role = message.get(
                "role"
            )

            content = str(
                message.get(
                    "content",
                    "",
                )
            ).strip()

            if (
                role
                in {
                    "user",
                    "assistant",
                }
                and content
            ):
                items.append(
                    f"{role}:"
                    f"{content[:150]}"
                )

        return "\n".join(items)

    @staticmethod
    def _resolve_system_power_action(
        text,
    ):
        """
        确定性解析系统级动作。

        不交给模型猜：
        shutdown / restart / sleep / lock / logout
        """
        q = str(text).strip().lower()

        checks = [
            (
                "restart",
                [
                    "重启电脑",
                    "重新启动电脑",
                    "重新启动",
                    "重启",
                    "restart",
                    "reboot",
                ],
            ),
            (
                "shutdown",
                [
                    "关闭电脑",
                    "把电脑关掉",
                    "把电脑关闭",
                    "电脑关机",
                    "关机",
                    "shutdown",
                    "power off",
                ],
            ),
            (
                "sleep",
                [
                    "让电脑睡眠",
                    "进入睡眠",
                    "电脑睡眠",
                    "睡眠",
                    "sleep",
                ],
            ),
            (
                "lock",
                [
                    "锁定电脑",
                    "锁定屏幕",
                    "锁屏",
                    "lock screen",
                    "lock",
                ],
            ),
            (
                "logout",
                [
                    "退出登录",
                    "注销当前账户",
                    "注销当前账号",
                    "注销",
                    "log out",
                    "logout",
                    "logoff",
                ],
            ),
        ]

        for action, phrases in checks:
            if any(
                phrase in q
                for phrase in phrases
            ):
                return action

        return None

    def _process_system_power(
        self,
        user_input,
        semantic,
    ):
        """
        系统级动作使用确定性执行链。

        Brain 不拥有 Windows 权限，只通过
        RemoteToolFactory -> Local Action Host。
        """
        action = (
            self._resolve_system_power_action(
                user_input
            )
        )

        if action is None:
            return None

        # 必须先把“原始用户命令”交给 Windows Permission Broker。
        try:
            self.tool_factory.permission.begin_request(
                user_input
            )
        except Exception as e:
            return {
                "ok": False,
                "semantic": semantic,
                "error": (
                    "无法建立系统操作授权请求："
                    f"{e}"
                ),
            }

        labels = {
            "shutdown": "关机",
            "restart": "重启",
            "sleep": "睡眠",
            "lock": "锁屏",
            "logout": "注销",
        }

        try:
            permit_result = (
                self.tool_factory
                .authorize_task(
                    capabilities=[
                        "power_control"
                    ],
                    targets=[
                        action
                    ],
                )
            )

            permit_text = str(
                permit_result
            )

            if not permit_text.startswith(
                "任务许可证已生效"
            ):
                try:
                    self.tool_factory.end_task()
                except Exception:
                    pass

                reply = (
                    f"{labels[action]}任务未执行："
                    f"{permit_text}"
                )

                return {
                    "ok": True,
                    "reply": reply,
                    "semantic": semantic,
                    "logs": (
                        "[System Control] "
                        "用户未授予本次 power_control。"
                        "\n清渊："
                        + reply
                    ),
                }

            # 真正动作仍在 Windows Action Host。
            # system_power 内部还会执行第二次系统级最终确认。
            result = (
                self.tool_factory
                .system_power(
                    action
                )
            )

            result_text = str(
                result
            )

            return {
                "ok": True,
                "reply": result_text,
                "semantic": semantic,
                "logs": (
                    "[System Control] "
                    f"确定性动作：{action}"
                    "\n"
                    + result_text
                ),
            }

        finally:
            # shutdown/restart/logoff 成功时进程可能来不及执行这里，
            # 但许可证本身仅驻留当前运行时；若还能执行则立即回收。
            try:
                self.tool_factory.end_task()
            except Exception:
                pass

    def process(
        self,
        source,
        text,
    ):
        # 新任务开始时清理上一任务的 cancel flag。
        try:
            self.runtime.clear_task_cancel()
        except Exception:
            try:
                self.runtime.cancel_event.clear()
            except Exception:
                pass

        raw = str(text).strip()

        if not raw:
            return {
                "ok": False,
                "error": "empty command",
            }

        user_input = raw

        semantic = None

        if source == "voice":
            semantic = (
                self.semantic_interpreter
                .normalize(
                    raw,
                    recent_context=(
                        self.recent_semantic_context()
                    ),
                )
            )

            user_input = semantic[
                "text"
            ]

        # ------------------------------------------------
        # 用户是在“教规则/纠正做法”，还是要“现在执行”？
        #
        # 教学内容必须在 Router/Task Permit 之前被截住。
        # ------------------------------------------------
        teaching_mode = (
            self.teach_classifier
            .classify(
                user_input
            )
        )

        if teaching_mode == "teach":
            teaching_reply = (
                self.knowledge
                .remember_teaching_rule(
                    user_input
                )
            )

            self.voice.speak(
                teaching_reply,
                allow_barge_in=True,
            )

            return {
                "ok": True,
                "reply": teaching_reply,
                "semantic": semantic,
                "logs": (
                    "[经验学习] 这是教学/纠正规则，"
                    "不会执行电脑操作。\\n"
                    f"清渊：{teaching_reply}"
                ),
            }

        # 明确长期记忆命令由 backend 自己处理。
        memory_reply = (
            self.knowledge
            .handle_command(
                user_input
            )
        )

        if memory_reply is not None:
            self.voice.speak(
                memory_reply,
                allow_barge_in=True,
            )

            return {
                "ok": True,
                "reply": memory_reply,
                "semantic": semantic,
                "logs": (
                    "[长期记忆] 本地读取，"
                    "无需电脑操作权限。\n"
                    f"清渊：{memory_reply}"
                ),
            }

        # ------------------------------------------------
        # 系统电源/会话控制属于高影响固定白名单动作。
        # 绝不交给 LLM 自由回答或决定是否调用工具。
        # ------------------------------------------------
        system_action = (
            self._resolve_system_power_action(
                user_input
            )
        )

        if system_action is not None:
            return self._process_system_power(
                user_input,
                semantic,
            )

        buffer = io.StringIO()

        with self.command_lock:
            with contextlib.redirect_stdout(
                buffer
            ):
                self.runtime.agent_busy.set()

                try:
                    self.core.process(
                        user_input
                    )
                finally:
                    self.runtime.agent_busy.clear()

        logs = buffer.getvalue()

        return {
            "ok": True,
            "semantic": semantic,
            "logs": logs,
        }

    def cancel_current_task(self):
        """
        中止 Brain 当前任务，并通知 Windows Action Host
        立即收回权限。
        """
        try:
            self.runtime.request_task_cancel()
        except Exception:
            try:
                self.runtime.cancel_event.set()
            except Exception:
                pass

        try:
            from .ipc_config import ACTION_URL
            from .ipc_http import post_json

            action_result = post_json(
                ACTION_URL + "/cancel",
                {},
                timeout=5,
            )
        except Exception as e:
            action_result = {
                "ok": False,
                "error": str(e),
            }

        return {
            "ok": True,
            "cancelled": True,
            "action_host": action_result,
        }

    def status(self):
        return {
            "ok": True,
            "service": (
                "qingyuan-brain-backend"
            ),
            "version": QINGYUAN_VERSION,
            "protocol_version": (
                BACKEND_PROTOCOL_VERSION
            ),
            "model_route": (
                self.model_router
                .status_text()
            ),
            "model_ctx": MODEL_NUM_CTX,
            "rag": (
                self.local_rag
                .status_text()
            ),
            "skills": len(
                self.skill_library
                .all_skills()
            ),
            "recent_messages": (
                MAX_RECENT_MESSAGES
            ),
            "vision_backend": True,
        }


def run():
    brain = BrainBackend()

    class Handler(
        BaseHTTPRequestHandler
    ):
        def _authorized(self):
            return (
                self.headers.get(
                    "X-Qingyuan-Token",
                    "",
                )
                == get_ipc_token()
            )

        def _send(
            self,
            code,
            data,
        ):
            payload = json.dumps(
                data,
                ensure_ascii=False,
            ).encode("utf-8")

            self.send_response(
                code
            )

            self.send_header(
                "Content-Type",
                (
                    "application/json; "
                    "charset=utf-8"
                ),
            )

            self.send_header(
                "Content-Length",
                str(len(payload)),
            )

            self.end_headers()

            try:
                self.wfile.write(
                    payload
                )
            except Exception:
                pass

        def _read_json(self):
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
                or 0
            )

            raw = self.rfile.read(
                length
            )

            if not raw:
                return {}

            try:
                data = json.loads(
                    raw.decode(
                        "utf-8"
                    )
                )

                return (
                    data
                    if isinstance(
                        data,
                        dict,
                    )
                    else {}
                )

            except Exception:
                return {}

        def do_GET(self):
            if not self._authorized():
                self._send(
                    403,
                    {
                        "ok": False,
                        "error": "unauthorized",
                    },
                )
                return

            path = self.path.split(
                "?",
                1,
            )[0]

            if path in {
                "/health",
                "/status",
            }:
                self._send(
                    200,
                    brain.status(),
                )
                return

            self._send(
                404,
                {
                    "ok": False,
                    "error": "not found",
                },
            )

        def do_POST(self):
            if not self._authorized():
                self._send(
                    403,
                    {
                        "ok": False,
                        "error": "unauthorized",
                    },
                )
                return

            path = self.path.split(
                "?",
                1,
            )[0]

            data = self._read_json()

            if path == "/vision/infer":
                prompt = str(
                    data.get(
                        "prompt",
                        "",
                    )
                )

                images = data.get(
                    "images",
                    [],
                )

                result = (
                    brain.backend_vision.infer(
                        prompt,
                        images,
                    )
                )

                self._send(
                    200,
                    result,
                )
                return

            if path == "/command":
                result = brain.process(
                    source=str(
                        data.get(
                            "source",
                            "keyboard",
                        )
                    ),
                    text=str(
                        data.get(
                            "text",
                            "",
                        )
                    ),
                )

                self._send(
                    200,
                    result,
                )
                return

            if path == "/cancel":
                result = (
                    brain.cancel_current_task()
                )

                self._send(
                    200,
                    result,
                )
                return

            if path == "/shutdown":
                brain.runtime.stop_event.set()

                self._send(
                    200,
                    {
                        "ok": True,
                        "shutting_down": True,
                    },
                )

                threading.Thread(
                    target=server.shutdown,
                    daemon=True,
                ).start()

                return

            self._send(
                404,
                {
                    "ok": False,
                    "error": "not found",
                },
            )

        def log_message(
            self,
            format,
            *args,
        ):
            return

    server = ThreadingHTTPServer(
        (
            BACKEND_HOST,
            BACKEND_PORT,
        ),
        Handler,
    )

    print(
        "=" * 60
    )
    print(
        "清渊 Brain Backend v5.3.3 已启动"
    )
    print(
        f"接口：http://"
        f"{BACKEND_HOST}:"
        f"{BACKEND_PORT}"
    )
    print(
        "模型路由："
        + brain.model_router
        .status_text()
    )
    print(
        "本地文档："
        + brain.local_rag
        .status_text()
    )
    print(
        "技能库："
        + str(
            len(
                brain.skill_library
                .all_skills()
            )
        )
    )
    print(
        "=" * 60
    )

    try:
        server.serve_forever(
            poll_interval=0.5
        )
    finally:
        brain.runtime.stop_event.set()
        server.server_close()
