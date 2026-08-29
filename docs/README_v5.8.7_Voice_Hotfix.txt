Qingyuan v5.8.7 Voice Latency + Barge-in + ASR Hallucination Guard

Fixes:
1. Real barge-in while Agent/Backend is busy and TTS is speaking.
2. End-of-speech silence reduced from 1.10s to 0.68s.
3. In active continuous conversation, a valid SenseVoice result is accepted
   immediately instead of forcing Whisper for every short sentence.
4. Whisper remains fallback/standby confirmation rather than mandatory second pass.
5. Removes literal vocabulary_prompt() injection from normal active decoding.
6. Rejects prompt-copy hallucinations such as "关键词：" and returns empty.
7. Low-confidence recognition failure is no longer converted into a fake user command.

Expected effect:
- Typical valid SenseVoice short utterance should avoid ~1-3s Whisper second-pass cost.
- User can speak while Qingyuan is talking; TTS is stopped after real barge speech.
- Silence/noise that yields "关键词：" is ignored rather than sent to the Brain.

This package does NOT modify:
data / memory / knowledge / skills / workspace / STT vocabulary /
SenseVoice model / Whisper model / CosyVoice model / virtual environments /
Coding Agent / Brain model routing (4B chat + 8B complex remains unchanged).
