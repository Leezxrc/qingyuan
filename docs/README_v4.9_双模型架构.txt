清渊 v4.9：Dual Model
==================================

默认：
日常聊天：
    qwen3:4b-instruct

复杂电脑任务：
    qwen3:8b

强模型负责：
- 语音后的 Semantic Interpreter
- 复杂任务 Planner 优化
- GUI / 浏览器 / 微信 / 文件等电脑任务的 Agent 推理

4B 负责：
- 普通聊天
- 简单问答
- 强模型不可用时自动回退

如果 qwen3:8b 尚未安装：
运行：
C:\MyAgent\tools\install_reasoning_model.bat

或命令：
ollama pull qwen3:8b

安全：
模型能力变强不代表权限变大。
Task Permit 仍然是唯一电脑操作授权层。
强模型仍然不能越过：
capability + target + 原始用户任务。

后续想换 14B：
只修改：
C:\MyAgent\qingyuan\config.py

REASONING_MODEL = "..."
