# 清渊 Voice Core 3.0 — Phase 1

目标
----
把旧的“请求一次才打开一次麦克风 / normal listen + barge listen”结构，
替换成 ABexit/ASR-LLM-TTS 风格的常驻单路语音入口：

Mic
 -> single always-on capture
 -> WebRTC VAD
 -> utterance queue
 -> SenseVoiceSmall primary
 -> Whisper fallback only when needed
 -> one transcript queue
 -> Qingyuan frontend
 -> 4B/8B Brain

本阶段解决
----------
1. 麦克风只有一个 owner。
2. 不再同时存在普通监听 + 打断监听两套请求。
3. 同一句话不会因为 barge-in 被投递两次。
4. Voice Core 在后台持续采集/VAD，而 /listen 只消费识别结果。
5. SenseVoice 是主识别；Whisper 只做 fallback。
6. 不再向 Whisper 注入“关键词：...” prompt，识别失败返回空。
7. TTS 播报开始时，Frontend 会告诉 Voice Core 进入 barge 模式；
   VAD 检测到强真人声后直接请求 /stop，随后同一句只投递一次。
8. 端口保持兼容：STT 仍为 127.0.0.1:8766。
9. qingyuan_stt_server.py 仍可按原启动方式运行，但它现在只是 Voice Core 3 入口。

本阶段没有改
----------
- Brain Backend 8770
- Local Action Host 8771
- Frontend control 8767
- TTS 8765
- Qwen3 4B 日常 / 8B 复杂任务路由
- Memory / RAG / Skills / Coding Agent
- Windows 权限边界
- data / memory / knowledge / skills / workspace
- data/stt_vocabulary.json
- voice/qingyuan_reference.wav
- CosyVoice 模型与环境
- SenseVoice 模型文件与 stt_env

注意
----
当前 CosyVoice 曾出现 RTF 28+ 的异常性能，本 Phase 1 不碰 TTS 模型。
先把“耳朵/打断/重复输入”稳定，再做 Phase 2 的实时 TTS/首块延迟优化。

安装后测试
----------
1. 退出所有清渊相关进程。
2. 将本 ZIP 内容覆盖到 C:\MyAgent。
3. 运行 tools\test_voice_core3_phase1.bat。
4. 启动 TTS。
5. 启动 qingyuan_stt_server.py（实际进入 Voice Core 3）。
6. 启动 Brain Backend。
7. 启动 Frontend。

暂时不要删除
------------
qingyuan_stt_server.py
qingyuan\voice.py
stt_env
CosyVoice
cosyvoice_env
voice
data
memory
knowledge
skills
workspace

等 Phase 2/3 完成并稳定后，再给最终“可删除旧语音文件”清单。
