清渊 模块化 v1
==============================

安装位置：
C:\MyAgent

本包只替换：
- C:\MyAgent\agent.py
- 新增 C:\MyAgent\qingyuan\ 文件夹

现有以下文件继续使用，不需要改：
- qingyuan_stt_server.py
- CosyVoice\qingyuan_tts_server.py
- qingyuan_launcher.py
- qingyuan_tray.py
- start_qingyuan.bat

目录：
agent.py                 入口
qingyuan\config.py       配置
qingyuan\runtime.py      运行状态 / 45秒会话 / 桌面任务状态
qingyuan\wake.py         唤醒词与近音
qingyuan\voice.py        STT/TTS/确认/键盘语音线程
qingyuan\desktop.py      Windows窗口/键鼠/任务授权/Chrome新标签
qingyuan\vision.py       Qwen3-VL屏幕分析/视觉定位/点击
qingyuan\workspace.py    workspace文件工具
qingyuan\memory.py       长期记忆
qingyuan\router.py       Intent Router
qingyuan\factory.py      Tool Factory / 动态工具集合
qingyuan\prompts.py      Base Prompt + 按任务 Prompt
qingyuan\agent_core.py   Ollama对话与工具循环
qingyuan\control.py      托盘本地API
qingyuan\app.py          主程序生命周期

最关键变化：
1. 普通聊天不向 Qwen 发送任何 tool schema。
2. Chrome 搜索只加载浏览器相关工具。
3. 窗口前台任务只加载 focus 相关工具。
4. 微信/GUI任务才加载视觉点击与键鼠工具。
5. 系统 Prompt 也按 intent 动态拼装。
6. agent.py 只剩入口，不再继续堆功能。

建议先测试：
1. 在吗
2. 清渊在吗（待机后）
3. 帮我用 Chrome 搜索 RTX 3080 驱动
4. 帮我把微信拉到前台
5. 在微信群聊 XXX 里发一句你好

如需回滚：
把你原来的单文件 agent.py 放回 C:\MyAgent\agent.py 即可；
新增的 qingyuan 文件夹不会影响旧版单文件 agent.py。
