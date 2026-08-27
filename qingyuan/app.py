import queue
import threading
import time

from .config import (
    ACTIVE_WINDOW_SECONDS,
    MODEL_NUM_CTX,
    MAX_RECENT_MESSAGES,
    WORKSPACE,
)
from .runtime import RuntimeState
from .voice import VoiceService
from .wake import normalize_command, is_standby_phrase
from .desktop import DesktopController
from .vision import VisionService
from .workspace import WorkspaceTools
from .memory import MemoryStore
from .wechat import WeChatTools
from .router import IntentRouter
from .factory import ToolFactory
from .agent_core import AgentCore
from .control import start_control_server
from .planner import Planner
from .verifier import Verifier
from .replanner import Replanner
from .semantic_interpreter import SemanticInterpreter
from .model_router import ModelRouter
from .permission import TaskPermissionBroker
from .system_tools import SystemTools
from .temp_cleanup import TempCleanupService
from .visual_reference_inbox import VisualReferenceInbox
from .visual_profile import migrate_legacy_wechat_assets
from .knowledge_memory import KnowledgeMemory
from .cognitive_router import CognitiveRouter
from .context_manager import ConversationContextManager
from .critic import PlanCritic
from .local_rag import LocalDocumentRAG
from .skills import SkillLibrary


def run():
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    runtime = RuntimeState()

    # 一次性把旧微信视觉资料迁移到通用视觉库。
    migrate_legacy_wechat_assets()

    temp_cleanup = TempCleanupService(
        runtime.stop_event
    )
    temp_cleanup.start()

    visual_reference_inbox = VisualReferenceInbox()
    visual_reference_inbox.start(
        runtime.stop_event
    )
    voice = VoiceService(runtime)

    permission = TaskPermissionBroker(
        runtime,
        voice,
    )

    desktop = DesktopController(
        runtime,
        voice,
        permission,
    )

    vision = VisionService(
        runtime,
        desktop,
        permission,
    )

    desktop.attach_vision(vision)

    system_tools = SystemTools(
        runtime,
        permission,
    )

    workspace = WorkspaceTools(
        runtime,
        voice,
        desktop.enumerate_visible_windows,
    )

    model_router = ModelRouter()

    knowledge = KnowledgeMemory(
        model_router
    )

    memory = MemoryStore(
        runtime,
        voice,
        knowledge=knowledge,
    )

    wechat = WeChatTools(
        runtime,
        desktop,
        vision,
    )

    router = IntentRouter()

    planner = Planner(
        model_router
    )

    verifier = Verifier(runtime)
    replanner = Replanner()

    semantic_interpreter = SemanticInterpreter(
        model_router
    )

    cognitive_router = CognitiveRouter()

    context_manager = ConversationContextManager(
        model_router
    )

    critic = PlanCritic(
        model_router
    )

    local_rag = LocalDocumentRAG()
    local_rag.start_watcher(
        runtime.stop_event,
        interval_seconds=60,
    )

    skill_library = SkillLibrary()

    factory = ToolFactory(
        desktop,
        vision,
        workspace,
        memory,
        wechat,
        permission,
        system_tools,
    )
    core = AgentCore(
        runtime,
        voice,
        memory,
        router,
        factory,
        planner,
        verifier,
        replanner,
        model_router,
        cognitive_router,
        context_manager,
        critic,
        local_rag,
        skill_library,
    )

    def standby_status_worker():
        """
        只负责 UI 状态提示，不参与 STT/VAD。

        连续会话 45 秒过期后只提示一次：
        🌙 清渊休息啦。
        """
        while not runtime.stop_event.is_set():
            if runtime.should_show_sleep_notice():
                print("\n🌙 清渊休息啦。")

            time.sleep(0.25)

    print("=" * 60)
    print("清渊已启动（模块化架构）")
    print(r"工作区：C:\MyAgent\workspace")
    print("输入方式：键盘 + 麦克风同时可用")
    print("语音待机唤醒词：清渊")
    print(f"连续对话窗口：{int(ACTIVE_WINDOW_SECONDS)} 秒")
    print(f"主模型上下文：{MODEL_NUM_CTX} tokens")
    print("Agent Core v6：认知路由 + RAG + Skills + Planner → Critic → Permit → Executor → Replan → Verifier")
    print(
        "本地文档："
        + local_rag.status_text()
    )
    print(
        f"技能库：{len(skill_library.all_skills())} 个技能"
    )
    print(
        "模型路由："
        + model_router.status_text()
    )
    print(f"短期聊天历史：最近 {MAX_RECENT_MESSAGES} 条消息")
    print("输入 exit / quit 退出")
    print("=" * 60)

    voice.speak(
        "清渊已启动。",
        allow_barge_in=False,
    )

    threads = [
        threading.Thread(
            target=start_control_server,
            args=(runtime, voice),
            daemon=True,
        ),
        threading.Thread(
            target=voice.keyboard_worker,
            daemon=True,
        ),
        threading.Thread(
            target=voice.voice_worker,
            daemon=True,
        ),
        threading.Thread(
            target=standby_status_worker,
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    def recent_semantic_context():
        """
        只给语义纠错器极少量上下文，
        不把整个对话历史重新塞进去。
        """
        items = []

        for message in core.messages[-4:]:
            if not isinstance(message, dict):
                continue

            role = message.get("role")
            content = str(
                message.get(
                    "content",
                    "",
                )
            ).strip()

            if (
                role in {"user", "assistant"}
                and content
            ):
                items.append(
                    f"{role}:{content[:150]}"
                )

        return "\n".join(items)

    try:
        while not runtime.stop_event.is_set():
            try:
                source, user_input = runtime.input_queue.get(
                    timeout=0.2
                )
            except queue.Empty:
                continue

            user_input = str(user_input).strip()
            if not user_input:
                continue

            runtime.mark_input_received()

            if source == "voice":
                raw_voice_input = user_input

                interpreted = (
                    semantic_interpreter.normalize(
                        raw_voice_input,
                        recent_context=(
                            recent_semantic_context()
                        ),
                    )
                )

                user_input = interpreted["text"]

                print(
                    f"\n你（语音）：{raw_voice_input}"
                )

                if interpreted.get("changed"):
                    print(
                        "[语义纠正] "
                        f"{raw_voice_input}"
                        "  →  "
                        f"{user_input}"
                        f"  (置信度 {interpreted['confidence']:.2f})"
                    )

            else:
                runtime.activate_conversation()

            runtime.agent_busy.set()
            voice.cancel_listen()

            command = normalize_command(user_input)

            try:
                # mic
                if command in {
                    "voice input on", "开启语音输入", "打开语音输入",
                    "语音输入开启", "恢复监听", "开始监听",
                }:
                    runtime.voice_listen_enabled = True
                    print("\n清渊：麦克风监听已经开启。")
                    voice.speak(
                        "麦克风监听已经开启。",
                        allow_barge_in=False,
                    )
                    runtime.activate_conversation()
                    continue

                if command in {
                    "voice input off", "关闭语音输入", "关掉语音输入",
                    "语音输入关闭", "停止语音输入", "停止监听",
                    "别听了",
                }:
                    runtime.voice_listen_enabled = False
                    voice.cancel_listen()
                    runtime.go_standby()
                    print("\n清渊：麦克风监听已经关闭，键盘仍然可用。")
                    voice.speak(
                        "麦克风监听已经关闭。",
                        allow_barge_in=False,
                    )
                    continue

                # TTS
                if command in {
                    "voice on", "开启语音", "打开语音", "语音开启",
                }:
                    runtime.voice_enabled = True
                    print("\n清渊：语音输出已经开启。")
                    voice.speak(
                        "语音输出已经开启。",
                        allow_barge_in=False,
                    )
                    runtime.activate_conversation()
                    continue

                if command in {
                    "voice off", "关闭语音", "关掉语音", "语音关闭",
                }:
                    voice.stop_speaking()
                    runtime.voice_enabled = False
                    print("\n清渊：语音输出已经关闭。")
                    runtime.activate_conversation()
                    continue

                # standby
                if is_standby_phrase(user_input):
                    voice.stop_speaking()
                    runtime.go_standby()
                    print("\n清渊：好。")
                    voice.speak("好。", allow_barge_in=False)
                    continue

                # exit
                if command in {
                    "exit", "quit", "退出清渊", "关闭清渊",
                }:
                    voice.stop_speaking()
                    print("\n清渊：下次见。")
                    runtime.stop_event.set()
                    voice.cancel_listen()
                    break

                # ------------------------------------------------
                # 明确的自然语言长期记忆管理
                #
                # “记住 / 修改 / 忘记 / 查询”
                # 只写清渊自己的 data\knowledge，
                # 不需要申请电脑控制权限。
                # ------------------------------------------------

                memory_reply = (
                    knowledge.handle_command(
                        user_input
                    )
                )

                if memory_reply is not None:
                    print(
                        f"\n清渊：{memory_reply}"
                    )

                    voice.speak(
                        memory_reply,
                        allow_barge_in=True,
                    )

                    runtime.activate_conversation()
                    continue

                # normal
                core.process(user_input)
                runtime.activate_conversation()

            finally:
                runtime.agent_busy.clear()

    except KeyboardInterrupt:
        runtime.stop_event.set()
        print("\n清渊：已退出。")

    finally:
        voice.shutdown_voice_services()
