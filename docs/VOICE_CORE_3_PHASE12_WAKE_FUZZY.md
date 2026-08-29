# Voice Core 3 Phase 1.2 — Wake Fuzzy Fix

Observed real ASR:
    现在几点了？亲元。

Phase 1.1 only normalized Qingyuan aliases when they appeared at the
beginning of the utterance. SenseVoice can place the vocative at the end.

Phase 1.2:
- adds 亲元 / 亲缘 / 清园 / 清圆 / 清远 and related aliases
- recognizes aliases at BOTH the beginning and the end
- canonicalizes end-form:
      现在几点了？亲元。
  into:
      清渊，现在几点了
- keeps replacement edge-scoped so ordinary body text is not globally altered

No VAD threshold change.
No Brain/Memory/RAG/Skills/TTS/data changes.
