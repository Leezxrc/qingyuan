清渊 v5.6.1 Launcher / Frontend Hotfix（CODE ONLY）

修复内容：
1. Frontend 的 8767 控制/健康接口提前启动，不再等待 Brain Backend 和“清渊已启动”TTS 完成。
2. Launcher 的 Frontend 等待时间 45 秒 -> 120 秒。
3. TTS / STT 首次启动等待时间延长到 300 秒。
4. 子服务启动 stdout/stderr 不再丢弃，分别记录：
   C:\MyAgent\logs\tts_startup.log
   C:\MyAgent\logs\stt_startup.log
   C:\MyAgent\logs\frontend_startup.log
   C:\MyAgent\logs\tray_startup.log
5. 子进程如果提前退出，Launcher 会在 qingyuan_launcher.log 中记录退出码和对应日志路径。
6. logs 目录每 7 天自动清理一次 *.log 文件。
   清理状态仅记录在 C:\MyAgent\logs\.last_weekly_cleanup。

安装：
- 完全退出清渊。
- 解压本 ZIP 到 C:\MyAgent，覆盖同名文件。
- 重新运行 tools\build_qingyuan_exe.bat 重新生成 Qingyuan.exe。
- 将新生成的 Qingyuan.exe 放在 C:\MyAgent 根目录并运行。

注意：
- 本包只包含代码和说明。
- 不包含、不覆盖 data / memory / knowledge / RAG / skills / workspace / STT vocabulary 等持久化数据。
- Backend Protocol 保持 8，不改变 Brain / Action Host 权限边界。
