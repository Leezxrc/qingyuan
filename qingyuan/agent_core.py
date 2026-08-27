import json
import traceback
from datetime import datetime

from ollama import chat

from .config import (
    MODEL,
    MODEL_NUM_CTX,
    REASONING_MODEL,
    REASONING_MODEL_NUM_CTX,
    REASONING_MODEL_KEEP_ALIVE,
    CHAT_MODEL_KEEP_ALIVE,
    MAX_RECENT_MESSAGES,
    DESKTOP_TASK_MAX_GUARD_LOOPS,
    ERROR_LOG_FILE,
)
from .prompts import PromptFactory


class AgentCore:
    def __init__(
        self,
        runtime,
        voice,
        memory,
        router,
        tool_factory,
        planner,
        verifier,
        replanner,
        model_router,
        cognitive_router,
        context_manager,
        critic,
        local_rag,
        skill_library,
        skill_learning,
    ):
        self.runtime = runtime
        self.voice = voice
        self.memory = memory
        self.router = router
        self.tool_factory = tool_factory
        self.planner = planner
        self.verifier = verifier
        self.replanner = replanner
        self.model_router = model_router
        self.cognitive_router = cognitive_router
        self.context_manager = context_manager
        self.critic = critic
        self.local_rag = local_rag
        self.skill_library = skill_library
        self.skill_learning = skill_learning
        self.prompt_factory = PromptFactory()
        self.messages = []

    @staticmethod
    def _role(message):
        if isinstance(message, dict):
            return message.get("role")
        return getattr(message, "role", None)

    def _runtime_messages(self, system_prompt, max_recent):
        recent = [
            m for m in self.messages
            if self._role(m) != "system"
        ]
        recent = recent[-max_recent:] if max_recent > 0 else []

        # 避免从孤立 tool result 开始。
        while recent and self._role(recent[0]) == "tool":
            recent.pop(0)

        return [
            {"role": "system", "content": system_prompt},
            *recent,
        ]

    @staticmethod
    def _is_context_overflow(exc):
        msg = str(exc).lower()
        return (
            "exceeds the available context size" in msg
            or "exceed_context_size_error" in msg
            or "context length" in msg
        )

    def _log_exception(self, where, exc):
        try:
            ERROR_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with ERROR_LOG_FILE.open("a", encoding="utf-8") as f:
                f.write("\n" + "=" * 70 + "\n")
                f.write(
                    f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {where}\n"
                )
                f.write(f"{type(exc).__name__}: {exc}\n")
                f.write(traceback.format_exc())
                f.write("\n")
        except Exception:
            pass

    @staticmethod
    def _parse_arguments(arguments):
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return dict(arguments) if arguments else {}

    def _cancelled(self):
        try:
            return bool(
                self.runtime.task_cancelled()
            )
        except Exception:
            try:
                return bool(
                    self.runtime.cancel_event.is_set()
                )
            except Exception:
                return False

    def process(self, user_input):
        try:
            self._process(user_input)
        except Exception as e:
            self._log_exception("process", e)
            print("\n【清渊运行错误】")
            print(f"{type(e).__name__}: {e}")
            print("清渊没有退出。详细错误已写入：")
            print(ERROR_LOG_FILE)

    def _process(self, user_input):
        original_user_input = (
            str(user_input).strip()
        )

        resolved_input = (
            original_user_input
        )

        replacements = []

        knowledge = getattr(
            self.memory,
            "knowledge",
            None,
        )

        if knowledge is not None:
            (
                resolved_input,
                replacements,
            ) = knowledge.resolve_references(
                original_user_input
            )

        if replacements:
            pretty = "；".join(
                f"{a} → {b}"
                for a, b in replacements
            )

            print(
                f"\n[长期记忆解析] {pretty}"
            )

        intent = self.router.route(
            resolved_input
        )

        action_intent = (
            self.router
            .is_action_intent(
                intent
            )
        )

        tool_required = (
            self.router
            .requires_tool(
                intent
            )
        )

        cognitive_mode = (
            self.cognitive_router.choose(
                resolved_input,
                intent,
            )
        )

        if cognitive_mode == "deep":
            selected_model = (
                self.model_router.for_planning()
            )
        else:
            selected_model = (
                self.model_router
                .for_intent(intent)
            )

        plan = self.planner.create(
            intent,
            resolved_input,
        )

        critic_notes = []

        if cognitive_mode == "deep":
            critic_notes = (
                self.critic.review(
                    plan
                )
            )

        # Task Permit 始终绑定用户真正说出的原始命令，
        # 不用解析后的内部文本替代。
        self.tool_factory.permission.begin_request(
            original_user_input
        )

        tools, available = self.tool_factory.create(intent)

        if (
            action_intent
            or cognitive_mode == "deep"
        ):
            print(
                f"\n[认知模式] {cognitive_mode}；"
                f"模型：{selected_model}"
            )

        internal_user_content = (
            original_user_input
        )

        if (
            resolved_input
            != original_user_input
        ):
            internal_user_content = (
                original_user_input
                + "\n[本地长期记忆解析后的内部目标："
                + resolved_input
                + "]"
            )

        self.messages.append({
            "role": "user",
            "content": internal_user_content,
        })

        self.context_manager.maybe_update(
            self.messages
        )

        guard_loops = 0
        guard_note = ""
        tool_results = []
        recovery_retries = {}
        skill_learning_done = False

        while True:
            if self._cancelled():
                print(
                    "\n清渊：当前任务已取消。"
                )
                try:
                    self.tool_factory.permission.end_task()
                except Exception:
                    pass
                break

            relevant_memory = (
                self.memory
                .relevant_memory_context(
                    resolved_input
                )
                if hasattr(
                    self.memory,
                    "relevant_memory_context",
                )
                else self.memory.memory_context()
            )

            rag_context = (
                self.local_rag
                .context_text(
                    resolved_input,
                    limit=4,
                )
            )

            skill_context = (
                self.skill_library
                .context_text(
                    resolved_input
                )
            )

            system_prompt = self.prompt_factory.build(
                intent,
                memory_context=relevant_memory,
                guard_note=guard_note,
                plan_text=plan.as_prompt_text(),
                conversation_summary=(
                    self.context_manager
                    .context_text()
                ),
                critic_notes=critic_notes,
                rag_context=rag_context,
                skill_context=skill_context,
            )

            runtime_messages = self._runtime_messages(
                system_prompt,
                MAX_RECENT_MESSAGES,
            )

            using_reasoning = (
                selected_model
                != MODEL
            )

            kwargs = {
                "model": selected_model,
                "messages": runtime_messages,
                "think": False,
                "stream": True,
                "keep_alive": (
                    REASONING_MODEL_KEEP_ALIVE
                    if using_reasoning
                    else CHAT_MODEL_KEEP_ALIVE
                ),
                "options": {
                    "num_ctx": (
                        REASONING_MODEL_NUM_CTX
                        if using_reasoning
                        else MODEL_NUM_CTX
                    )
                },
            }

            # 关键：普通聊天完全不传 tools。
            if tools:
                kwargs["tools"] = tools

            if self._cancelled():
                print(
                    "\n清渊：当前任务已取消。"
                )
                break

            try:
                stream = chat(**kwargs)
            except Exception as first_error:
                if not self._is_context_overflow(first_error):
                    raise

                print("\n[上下文] 正在自动缩短历史后重试……")
                kwargs["messages"] = self._runtime_messages(
                    system_prompt,
                    2,
                )
                stream = chat(**kwargs)

            content = ""
            thinking = ""
            tool_calls = []
            desktop_active_at_start = (
                self.runtime.desktop_task_is_active()
            )
            started_printing = False

            for chunk in stream:
                if self._cancelled():
                    print(
                        "\n清渊：当前任务已取消。"
                    )
                    break

                message = chunk.message

                piece_thinking = getattr(message, "thinking", None)
                if piece_thinking:
                    thinking += piece_thinking

                piece = getattr(message, "content", None)
                if piece:
                    # active 桌面任务期间不把“正在操作”之类假进度打印给用户。
                    if not desktop_active_at_start:
                        if not started_printing:
                            print("\n清渊：", end="", flush=True)
                            started_printing = True
                        print(piece, end="", flush=True)
                    content += piece

                calls = getattr(message, "tool_calls", None)
                if calls:
                    tool_calls.extend(calls)

            if started_printing:
                print()

            should_save = (
                bool(tool_calls)
                or not self.runtime.desktop_task_is_active()
            )
            if should_save and (content or thinking or tool_calls):
                self.messages.append({
                    "role": "assistant",
                    "content": content,
                    "thinking": thinking,
                    "tool_calls": tool_calls,
                })

            # no tool call
            if not tool_calls:
                # 对必须依赖真实工具的意图：
                # 在任何真实工具都还没执行前，
                # 不允许模型仅用文字回答或自我拒绝。
                if tool_required:
                    # 只认当前这一次请求真实产生的工具结果，
                    # 避免上一轮历史 tool message 误判为本轮已执行。
                    if not tool_results:
                        guard_loops += 1

                        if guard_loops > DESKTOP_TASK_MAX_GUARD_LOOPS:
                            print(
                                "\n[执行器] 模型连续没有调用实际工具，"
                                "本次任务已停止。"
                            )
                            break

                        print(
                            "\n[执行器] 当前请求需要真实工具数据，"
                            "正在强制进入工具调用……"
                        )

                        guard_note = (
                            "\n【执行器强制状态】\n"
                            "当前请求必须通过已加载工具获取真实结果。"
                            "\n不得猜测，不得声称无法访问，"
                            "不得让用户手动查看。"
                            "\n必须立即调用当前已加载工具。"
                            "\n只有工具真实失败后才能报告失败原因。"
                        )
                        continue

                if self.runtime.desktop_task_is_active():
                    guard_loops += 1
                    if guard_loops > DESKTOP_TASK_MAX_GUARD_LOOPS:
                        print(
                            "\n[桌面执行器] 连续多轮没有完成任务，"
                            "已为安全起见结束本次授权。"
                        )
                        self.runtime.clear_desktop_task()
                        break

                    print(
                        "\n[桌面执行器] 任务仍在进行，自动继续下一步……"
                    )
                    actions = sorted(
                        self.runtime.desktop_action_types()
                    )
                    guard_note = (
                        "\n【执行器强制状态】\n"
                        "当前桌面任务已经统一授权且仍 active。"
                        f"\n已真实动作：{actions}"
                        "\n不得只输出文字，必须继续调用实际工具。"
                        "\n任务真正完成后调用 end_desktop_task。"
                    )
                    continue

                if action_intent:
                    verification = self.verifier.verify(
                        plan,
                        tool_results,
                    )

                    if not verification.success:
                        # 如果工具已经真实失败，就停止，不让模型继续假装成功。
                        if tool_results:
                            failure_text = (
                                "任务没有完成："
                                + verification.reason
                            )
                            print(
                                "\n清渊："
                                + failure_text
                            )
                            if self.runtime.voice_enabled:
                                self.voice.speak(
                                    failure_text
                                )
                            self.runtime.activate_conversation()
                            break

                        # 没有真实工具调用时继续强制执行。
                        guard_loops += 1
                        if guard_loops > DESKTOP_TASK_MAX_GUARD_LOOPS:
                            print(
                                "\n[执行器] 未能进入真实工具执行，任务停止。"
                            )
                            break

                        guard_note = (
                            "\n【Verifier】\n"
                            "当前任务还没有任何可验证的真实工具动作。"
                            "\n不要输出完成结果，立即继续调用工具。"
                        )
                        continue

                # 成功任务沉淀为候选技能。
                #
                # 这里只学习流程：
                # - 不学习权限
                # - 不记录具体消息正文/群号等一次性参数
                # - 至少成功两次才晋升 learned
                if (
                    action_intent
                    and tool_results
                    and not skill_learning_done
                ):
                    try:
                        verification = self.verifier.verify(
                            plan,
                            tool_results,
                        )

                        if verification.success:
                            self.skill_learning.record_success(
                                intent=intent,
                                user_goal=original_user_input,
                                plan_steps=plan.steps,
                                tool_results=tool_results,
                                verifier_result=(
                                    verification.reason
                                ),
                                used_capabilities=(
                                    plan.required_capabilities
                                ),
                            )

                            skill_learning_done = True

                    except Exception as e:
                        print(
                            f"\n[技能学习] 跳过：{e}"
                        )

                if content.strip():
                    if self.runtime.voice_enabled:
                        self.voice.speak(content)
                    self.runtime.activate_conversation()
                break

            if self._cancelled():
                try:
                    self.tool_factory.permission.end_task()
                except Exception:
                    pass
                print(
                    "\n清渊：当前任务已取消。"
                )
                break

            # execute tools
            for tool_call in tool_calls:
                if self._cancelled():
                    print(
                        "\n清渊：当前任务已取消，"
                        "后续工具不会执行。"
                    )
                    break
                name = tool_call.function.name
                args = self._parse_arguments(
                    tool_call.function.arguments
                )
                fn = available.get(name)

                if self._cancelled():
                    result = "任务已取消：工具未执行。"

                elif fn is None:
                    result = f"当前任务没有加载工具：{name}"
                else:
                    try:
                        result = fn(**args)
                    except Exception as e:
                        result = f"工具执行失败：{e}"

                result_text = str(result)

                self.messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": result_text,
                })

                tool_results.append(
                    (name, result_text)
                )

                failure_markers = [
                    "失败",
                    "无法",
                    "没有找到",
                    "不在前台",
                    "置信度不足",
                    "拒绝执行",
                ]

                if any(
                    marker in result_text
                    for marker in failure_markers
                ):
                    retry_count = (
                        recovery_retries.get(
                            name,
                            0,
                        )
                    )

                    decision = (
                        self.replanner.decide(
                            intent,
                            name,
                            result_text,
                            retry_count,
                        )
                    )

                    if decision.should_retry:
                        recovery_retries[name] = (
                            retry_count + 1
                        )

                        guard_note = (
                            "\n【Recovery / Replan】\n"
                            f"刚才工具 {name} 失败。"
                            f"\n恢复策略：{decision.strategy}"
                            f"\n说明：{decision.note}"
                            "\n只能在当前已授权任务范围内恢复，"
                            "不得申请新目标或扩大权限。"
                            "\n请立即使用现有工具按恢复策略继续执行。"
                        )

                        break

            else:
                guard_note = ""

            if guard_note:
                continue
