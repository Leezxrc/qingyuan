清渊 v5.0：Frontend / Brain Backend Split
============================================================

这是一次架构重构，不是单独增加某个功能。


一、当前结构

Windows Frontend
    |
    | HTTP IPC + 本地随机 Token
    v
Brain Backend
    |
    | 请求真实电脑动作
    v
Local Action Host
    |
    v
Task Permit / Windows


逻辑上：

[Frontend]
麦克风
音箱
键盘
托盘
Windows 本地状态

        |
        v

[Brain Backend]
4B / 8B
Semantic Interpreter
Memory
RAG
Skills
Planner
Critic
Agent Core
Replanner
Verifier

        |
        v

[Local Action Host]
Task Permit
屏幕
窗口
鼠标
键盘
文件
微信


二、安全边界

最重要的变化：

Brain Backend 不直接拥有 Windows 权限。

它只能请求：

http://127.0.0.1:8771

Local Action Host 再调用原来的：

TaskPermissionBroker

所以即使以后 Brain Backend 放到另一台 AI 机器，
电脑真实权限仍然留在 Windows 这一侧。


三、端口

Frontend 原控制接口：
127.0.0.1:8767

TTS：
127.0.0.1:8765

STT：
127.0.0.1:8766

Brain Backend：
127.0.0.1:8770

Local Action Host：
127.0.0.1:8771


四、IPC 身份验证

第一次运行自动生成：

C:\MyAgent\data\ipc_token.txt

Brain Backend 和 Action Host 的请求必须带同一个 token。

默认服务只监听 127.0.0.1，
所以当前不会暴露给局域网。


五、如何启动

原来的：

C:\MyAgent\agent.py

现在就是 Frontend 入口。

Frontend 检查：

http://127.0.0.1:8770/health

如果本地 Brain Backend 没启动，
会自动运行：

C:\MyAgent\qingyuan_backend.py

所以旧 launcher 仍然可以继续使用。


调试也可以直接运行：

C:\MyAgent\start_qingyuan_split_debug.bat


六、原功能保留

- 原语音
- 唤醒
- Task Permit
- 微信
- 桌面控制
- Vision
- 长期记忆
- 自然语言记忆
- 本地文档 RAG
- Skills
- Planner
- Critic
- Replanner
- Verifier

都保留。


七、当前还没有彻底远程化的部分

VisionService 当前仍在 Windows Action Host 内调用视觉模型。

也就是说：
当前版本已经完成“Brain 与 Windows 动作安全边界”的拆分，
但如果未来真的把 Backend 放到另一台机器，
还应该继续做：

Windows 截图
    ->
Backend Vision Inference
    ->
返回 bbox / 分析结果
    ->
Windows Action Host 执行动作

这样 AI 机器才真正负责所有模型推理。

这是下一阶段再做，不应该和这次重构一次改太多。


八、以后换 AI 专用机器

最终目标：

Windows 主机
    Frontend + Local Action Host

局域网
        ↓

AI 主机
    Brain Backend
    Ollama
    4B/8B/14B
    RAG
    Skills
    Vision

Windows 仍然是最终权限持有者。


九、升级原则

从 v5.0 开始：

前端升级
= UI / Voice / Desktop / Permission

后端升级
= Model / Reasoning / RAG / Skill / Memory

以后不再把两边混在一个 app.py 里继续堆功能。
