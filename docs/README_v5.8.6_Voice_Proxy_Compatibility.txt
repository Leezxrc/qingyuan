Qingyuan v5.8.6 Voice Proxy Compatibility Hotfix

Fix:
1. Keeps RemoteVoiceProxy -> VoiceService compatibility from v5.8.5.
2. Adds a defensive AgentCore fallback:
   - if speak_response exists, use it;
   - otherwise build the same spoken summary locally and call speak().
3. A mismatched/older remote voice proxy can no longer crash the whole turn.

Important:
This does NOT start the TTS service. If Frontend prints:
  [语音] 清渊语音服务没有启动。
start C:\MyAgent\CosyVoice\qingyuan_tts_server.py separately.

This package does not contain/modify:
data, memory, knowledge, skills, workspace, STT vocabulary,
SenseVoice, Whisper, CosyVoice model files, or virtual environments.
