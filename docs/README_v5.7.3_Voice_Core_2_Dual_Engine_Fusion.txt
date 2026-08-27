清渊 v5.7.3 - Voice Core 2.0 双引擎融合热修

本版针对实测：
- SenseVoice：庭缘雨伞的英文是什么？
- Whisper：清渊语散的英文是什么。
- v5.7.2 因 Whisper 命中“清渊”，错误地用 Whisper 整句覆盖 SenseVoice，导致“雨伞”退化成“语散”。

本版策略：
- SenseVoice 作为正文主识别结果。
- Whisper 主要承担唤醒词确认和 SenseVoice 极短/失败时兜底。
- 双引擎都检测到清渊近音时，只把 SenseVoice 中对应的两字唤醒词规范为“清渊”。
- 不再因为 Whisper 仅命中“清渊”或用户词库就覆盖整个 SenseVoice 句子。
- 例如 SenseVoice“庭缘雨伞的英文是什么” + Whisper“清渊语散的英文是什么” -> 最终“清渊雨伞的英文是什么”。
- v5.7.2 的自适应 WebRTC + RMS 双门控参数保持不变。

安装：
1. 关闭当前 STT 服务。
2. 解压本包到 C:\MyAgent，覆盖同名文件。
3. 重新启动 STT；SenseVoice 已缓存，不应再次下载完整模型。
4. 再启动 Frontend。

本包为 CODE ONLY：
- 不包含、不覆盖 data / memory / knowledge / RAG / skills / workspace。
- 不包含、不覆盖 stt_vocabulary.json。
