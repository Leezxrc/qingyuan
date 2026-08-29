# Voice Core 3 Phase 1.3 — ASR Cleanup

Based on real test output:
- "现在几点了？情缘。" was not normalized as Qingyuan.
- One SenseVoice result duplicated the same command:
  "清渊，现在几点了？清渊现在几点了？"

Changes:
- add 情缘 / 情元 as edge-scoped Qingyuan wake aliases
- collapse duplicate Qingyuan-prefixed command inside a single ASR transcript
- no VAD threshold changes
- no model changes
- no Brain/Memory/RAG/Skills/TTS/data changes
