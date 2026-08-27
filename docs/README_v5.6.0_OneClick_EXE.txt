清渊 v5.6.0 —— 一键 EXE 启动器
============================================================

目标
----
日常使用时只双击：

C:\MyAgent\Qingyuan.exe

Qingyuan.exe 只负责“启动与监督”，不会把模型、Python 环境、记忆数据硬塞进 EXE。
这种方式更稳定，也保持清渊现有 Frontend / Brain Backend / Action Host 分层。

启动链
------
Qingyuan.exe
  -> CosyVoice TTS : 8765
  -> Faster-Whisper STT : 8766
  -> Frontend : 8767
       -> 自动启动/连接 Brain Backend : 8770
       -> Local Action Host : 8771
       -> Desktop Pet（v5.5+）
  -> Tray

特点
----
1. 日常启动无 CMD 黑框。
2. 防止 Qingyuan.exe 重复启动多个监督进程。
3. EXE 放在 C:\MyAgent 根目录，路径自动以 EXE 所在目录为基准。
4. Frontend 退出后自动清理 TTS/STT/Tray；Backend 也有崩溃兜底清理。
5. 启动日志写入 C:\MyAgent\logs\qingyuan_launcher.log。
6. 原来的 debug BAT 不删除，出问题时仍可以用它查看终端日志。

安装升级包
----------
1. 完全退出清渊。
2. 解压本包到 C:\MyAgent，覆盖同名源码。
3. 本包不会覆盖 memory/data/knowledge/RAG/skills/workspace 等用户持久化数据。

第一次生成 EXE（本机方式）
-------------------------
双击：

C:\MyAgent\tools\build_qingyuan_exe.bat

它只会在 C:\MyAgent\.venv 中检查/安装 PyInstaller，然后生成：

C:\MyAgent\Qingyuan.exe

之后日常使用只双击 Qingyuan.exe。

桌面快捷方式（可选）
--------------------
PowerShell 运行：

powershell -ExecutionPolicy Bypass -File C:\MyAgent\tools\create_qingyuan_desktop_shortcut.ps1

GitHub Actions 构建（可选）
--------------------------
本包还带：

.github\workflows\build-qingyuan-exe.yml

提交到 GitHub 后，可以在 Actions 中手动运行 Build Qingyuan EXE，
由 Windows runner 生成 Qingyuan.exe artifact。

为什么不把所有东西硬打成一个巨型 EXE
------------------------------------
清渊目前依赖：
- .venv
- stt_env
- cosyvoice_env
- Ollama
- Faster-Whisper 模型
- CosyVoice 模型
- 用户 memory/data/knowledge/RAG/skills

把这些全部封进 onefile EXE 会非常巨大，启动慢，模型更新困难，
而且容易破坏用户持久化数据隔离。

因此 v5.6.0 的原则是：
“一个 EXE 入口，一套模块化运行环境”。

持久化安全
----------
本升级包不包含：
- data
- memory
- knowledge
- RAG 数据
- learned skills 数据
- workspace
- STT vocabulary
- 用户配置内容
