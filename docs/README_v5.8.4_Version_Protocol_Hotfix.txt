Qingyuan v5.8.4 Version / Protocol Hotfix

Purpose:
Restore BACKEND_PROTOCOL_VERSION after v5.8.3 accidentally replaced version.py
without preserving the existing backend protocol constant.

Restored:
QINGYUAN_VERSION = "5.8.4"
BACKEND_PROTOCOL_VERSION = 7

This package does not contain or modify:
data / memory / knowledge / skills / workspace / models / STT vocabulary /
CosyVoice / SenseVoice / virtual environments.
