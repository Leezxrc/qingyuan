Qingyuan v5.8.5 RemoteVoiceProxy Compatibility Hotfix

Problem:
AgentCore v5.8.2+ calls voice.speak_response(), but Brain Backend uses
RemoteVoiceProxy, which previously implemented only speak().

Fix:
RemoteVoiceProxy now inherits VoiceService's response-preparation interface.
Its own speak() remains the remote Action Host implementation, therefore
speak_response() summarizes locally in the Brain and then delegates the
actual speech request to the Windows front end.

This package does NOT contain or modify:
data / memory / knowledge / skills / workspace / STT vocabulary /
SenseVoice / Whisper / CosyVoice / models / virtual environments.
