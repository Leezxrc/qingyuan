清渊 v5.7.1 Voice Core 2.0 Hotfix
=================================

本补丁针对 v5.7.0 实机测试暴露的语音误触发问题。

主要修改：
1. WebRTC VAD 默认 aggressiveness 从 2 提升到 3。
2. 新增 WebRTC + RMS 双门控：
   - 待机状态采用更严格的最低能量门槛。
   - 连续对话保持较低门槛，避免正常讲话难触发。
   - TTS 打断模式使用最高门槛，减少扬声器漏音自打断。
3. 待机启动确认提升到约 0.34 秒连续真人语音。
4. 打断启动确认提升到约 0.36 秒，并提高能量门槛。
5. 启动播报从“清渊已启动”改为“已启动”，避免清渊把自己的启动语当成唤醒词。
6. Frontend 主动取消 /listen 时，ConnectionReset/BrokenPipe 被视为正常竞态，不再刷整屏 traceback。
7. Voice Core 检查脚本现在真正验证 PyTorch + FunASR AutoModel，不再出现“funasr 可 import 但缺 torch”的假 OK。
8. 完整依赖安装脚本补充 PyTorch CPU + torchaudio。

可调环境变量：
QINGYUAN_WEBRTC_VAD_MODE       默认 3
QINGYUAN_STANDBY_MIN_RMS       默认 0.012
QINGYUAN_ACTIVE_MIN_RMS        默认 0.009
QINGYUAN_BARGE_MIN_RMS         默认 0.035

如果待机仍然过于灵敏，可先把 QINGYUAN_STANDBY_MIN_RMS 提到 0.014 或 0.016。
如果正常说话很难触发，可降低到 0.010。

安装：
1. 完全退出清渊。
2. 解压本 ZIP 到 C:\MyAgent 并覆盖同名代码文件。
3. 不需要重新安装依赖（你已安装 torch/FunASR 时）。
4. 重新分别启动 TTS、STT、Frontend 进行实测。
5. 等 SenseVoice 模型首次下载完成后再比较最终识别精度。

本包仅包含代码/说明，不包含：
data、memory、knowledge、RAG、learned skills、workspace、stt_vocabulary.json 等用户持久化数据。
