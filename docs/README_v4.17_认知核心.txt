清渊 v4.17：Cognitive Core
==================================================

本版目标：
不再继续堆零碎功能，开始提升“判断力”和“上下文能力”。

1. Cognitive Router

fast：
    简短日常聊天
    -> 4B 快速回答

deep：
    复杂问题
    多条件问题
    规划
    分析
    电脑任务
    -> 8B 深度模式


2. Planner + Critic

复杂任务：
    Planner 先生成计划
    Critic 再检查一次计划

Critic 只能指出：
    漏步骤
    顺序问题
    风险
    是否需要额外验证

Critic 不允许：
    增加权限
    增加目标
    改变用户原始任务


3. Rolling Conversation Summary

不再只靠最近 4 条消息。

当对话变长时：
    较旧内容
      ->
    自动压缩成历史摘要

文件：
    C:\MyAgent\data\conversation_summary.json

最近对话仍保留，
旧内容以摘要形式继续进入上下文。


4. Relevant Memory Retrieval

不再每次把所有长期记忆塞进 prompt。

当前问题：
    “在家庭群里发消息”

只检索：
    家庭群 = 9652711

而不是把整个 knowledge 库全部加载。


5. 当前认知链

Voice / Keyboard
    ↓
Semantic Interpreter
    ↓
Long-term Reference Resolution
    ↓
Cognitive Router
    ↓
Relevant Memory Retrieval
    ↓
Planner
    ↓
Critic
    ↓
Task Permit
    ↓
Executor
    ↓
Replanner
    ↓
Verifier


注意：

v4.17 能明显提高“像一个真正智能体”的程度，
但底层模型仍是本地 4B / 8B，
因此不能等同于大型云端模型。

如果之后继续提高能力，下一阶段应考虑：
- 14B/更强本地 reasoning model
- 本地文档 RAG
- Skills / Procedure Library
- Web / information retrieval
- 更高级的任务状态机
