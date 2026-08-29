import ast
from pathlib import Path

p = Path(r"C:\MyAgent\qingyuan_voice_core.py")
text = p.read_text(encoding="utf-8")
ast.parse(text)

assert '"亲元"' in text
assert '"亲缘"' in text
assert '"清园"' in text
assert "Wake alias at the end" in text
assert 'return "清渊，" + body' in text

# Extract only the alias tuple + normalize function without importing heavy ASR deps.
start = text.index("WAKE_ALIASES = (")
func_start = text.index("def _normalize_wake_alias", start)
func_end = text.index("def _is_noise_hallucination", func_start)

snippet = text[start:func_end]
ns = {}
exec(snippet, ns)

f = ns["_normalize_wake_alias"]

cases = {
    "秦元，现在几点了？": "清渊，现在几点了？",
    "清约，现在几点了？": "清渊，现在几点了？",
    "现在几点了？亲元。": "清渊，现在几点了",
    "现在几点了，亲缘": "清渊，现在几点了",
    "清渊，现在几点了": "清渊，现在几点了",
}

for raw, expected in cases.items():
    got = f(raw)
    assert got == expected, (raw, got, expected)
    print(f"[OK] {raw} -> {got}")

print("[OK] syntax")
print("[OK] wake aliases work at beginning and end")
print("[OK] 亲元/亲缘/清园 family covered")
print("ALL_TESTS_OK")
