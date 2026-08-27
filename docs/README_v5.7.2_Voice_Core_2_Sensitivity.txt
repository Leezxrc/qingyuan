清渊 v5.7.2 - Voice Core 2.0 灵敏度回调补丁

问题：
v5.7.1 为减少误触发，将待机固定 RMS 门槛提高到 0.012；在部分 USB 麦克风上会过严，导致正常讲话也无法触发。

本版调整：
- 保留 WebRTC VAD mode 3。
- 保留 WebRTC + RMS 双门控。
- 启动校准阈值从固定最低 0.008 改为自适应：max(环境底噪*8, 0.0025)。
- 待机固定最低 RMS：0.0035。
- 连续对话固定最低 RMS：0.0025。
- Barge-in 固定最低 RMS：0.012。
- 待机确认窗：0.26 秒，语音占比 65%。
- 连续对话确认窗：0.14 秒，语音占比 55%。
- 打断确认窗：0.24 秒，语音占比 72%。
- 启动时额外打印“待机实际能量门槛”和“连续对话实际能量门槛”，便于继续实测调参。

安装：
1. 完全退出清渊 / STT。
2. 解压本包到 C:\MyAgent，覆盖同名文件。
3. 重新启动 STT 和 Frontend。

注意：
- SenseVoice 下载提示“Still waiting to acquire lock”通常表示另一个 STT/SenseVoice 进程仍在下载同一模型。请确保只运行一个 qingyuan_stt_server.py。
- 不要在仍有下载进程时手动删除 ModelScope lock 文件。
- 本包不包含、不覆盖 data / memory / knowledge / RAG / skills / workspace / stt_vocabulary.json。
