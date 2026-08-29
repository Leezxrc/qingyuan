Qingyuan v5.8.3 - Voice Stability Finalization

Scope: code only. No memory/data/knowledge/skills/workspace/STT vocabulary/model files are included.

Changes:
1. Refresh active-conversation window at TTS start/end so a long answer does not force the next turn to say the wake word again.
2. Filter current-playing and trailing TTS partial echoes, not only full post-playback matches.
3. Add 220 ms post-TTS acoustic-tail cooldown before opening the normal listening window.
4. Rebalance barge-in gate: 0.009 minimum RMS, 0.28 s confirmation, 78% voiced-window ratio.
5. Print the calibrated barge-in threshold at STT startup for real-device tuning.

Install: stop Qingyuan, extract this ZIP over C:\MyAgent, then restart TTS/STT/agent.py.
Test: C:\MyAgent\tools\test_voice_stability_v583.bat
