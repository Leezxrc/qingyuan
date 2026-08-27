清渊 v4.8：Semantic Interpreter
==================================

新链路：

Whisper
  ↓
Semantic Interpreter
  ↓
Intent Router
  ↓
Planner
  ↓
Task Permit
  ↓
Executor / Replanner / Verifier

Semantic Interpreter：
- 专门修正语音识别的同音/近音错字
- 不拥有电脑权限
- 不调用 tools
- 不允许新增用户没要求的动作
- 必须原样保留数字、群号、路径、URL
- 置信度 >= 0.82 才采用纠正结果
- 键盘输入完全不经过语义纠错

示例：
微信群条9652711中发送你好
  ->
微信群聊9652711中发送你好

同时 Planner 对数字群号增加兜底抽取：
即使“微信群聊”仍被听错，只要附近有 4 位以上数字，
会优先把数字作为 chat_identifier。
