Qingyuan v5.8.2 - TTS Spoken Summary / Screen Full Answer
=========================================================

Purpose
-------
Keep the full assistant response on screen, but avoid reading long technical content,
code blocks, file paths, diffs, and logs word-for-word through TTS.

Behavior
--------
1. Short normal chat: spoken text remains unchanged.
2. Coding/technical long answers: TTS uses a concise deterministic spoken summary.
3. Full response is still printed/stored as before.
4. Coding read-only tasks say that no files were modified, based on real tool results.
5. Coding write tasks only say modification passed verification when the current session
   actually contains code_write_file + successful code_finish_session.
6. Code blocks and full paths are never required to be spoken aloud.
7. This is deterministic local response shaping; it does NOT add an extra LLM call,
   so it does not add another model-generation delay.

Files changed
-------------
qingyuan/voice.py
qingyuan/agent_core.py
qingyuan/version.py

Test
----
C:\MyAgent\tools\test_tts_summary_v582.bat

Safety / persistence
--------------------
This package contains code/docs/tests only. It does not include or overwrite data,
memory, knowledge, skills, workspace, STT vocabulary, models, or virtual environments.
