import ast
import re
from pathlib import Path

p = Path(r"C:\MyAgent\qingyuan_voice_core.py")
text = p.read_text(encoding="utf-8")
ast.parse(text)

assert '"情缘"' in text
assert '"情元"' in text
assert "def _collapse_repeated_command" in text
assert "text = _collapse_repeated_command(text)" in text

# Extract the two lightweight helpers only.
wake_start = text.index("WAKE_ALIASES = (")
noise_start = text.index("def _is_noise_hallucination", wake_start)
wake_snippet = text[wake_start:noise_start]

collapse_start = text.index("def _collapse_repeated_command")
sanitize_start = text.index("def _sanitize", collapse_start)
collapse_snippet = text[collapse_start:sanitize_start]

ns = {"re": re}
exec(wake_snippet, ns)
exec(collapse_snippet, ns)

wake = ns["_normalize_wake_alias"]
collapse = ns["_collapse_repeated_command"]

cases = {
    "现在几点了？情缘。": "清渊，现在几点了",
    "情缘，现在几点了？": "清渊，现在几点了？",
}
for raw, expected in cases.items():
    got = wake(raw)
    assert got == expected, (raw, got, expected)
    print(f"[OK] wake: {raw} -> {got}")

raw = "清渊，现在几点了？清渊现在几点了？"
got = collapse(raw)
assert got == "清渊，现在几点了？", got
print(f"[OK] collapse: {raw} -> {got}")

print("[OK] syntax")
print("[OK] 情缘/情元 wake aliases")
print("[OK] single-result repeated command collapse")
print("ALL_TESTS_OK")
