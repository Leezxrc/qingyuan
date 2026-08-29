# Voice Core 3.0 Phase 1.1 Stability

This patch tunes the Phase 1 always-on voice pipeline using the user's
measured room noise and real recognition logs.

Changes:
- WebRTC VAD mode 2 -> 3 (more aggressive non-speech rejection)
- minimum RMS 0.0018 -> 0.0028
- noise multiplier 5 -> 6
- minimum voiced speech 180 ms -> 260 ms
- end silence 540 ms -> 480 ms
- whole-utterance voiced-frame ratio gate >= 0.38
- whole-utterance RMS gate >= 0.0024
- normalize common Qingyuan near-homophones at utterance start:
  秦元 / 清约 / 庆元 / 清源 / 青渊 / etc. -> 清渊
- reject common noise hallucinations:
  The. / 字幕by... / 感谢观看 / subtitles by / thanks for watching

Does NOT modify:
Brain 4B/8B routing, Memory, RAG, Skills, Coding Agent, data,
stt_vocabulary.json, CosyVoice, model files, or environments.
