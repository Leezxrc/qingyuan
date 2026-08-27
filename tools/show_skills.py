import json
from pathlib import Path

roots = [
    ("builtin", Path(r"C:\MyAgent\skills\builtin")),
    ("user", Path(r"C:\MyAgent\skills\user")),
    ("candidate", Path(r"C:\MyAgent\skills\candidates")),
    ("learned", Path(r"C:\MyAgent\skills\learned")),
]

for label, folder in roots:
    print()
    print("=" * 60)
    print(label.upper())
    print("=" * 60)

    if not folder.exists():
        print("(empty)")
        continue

    files = sorted(folder.glob("*.json"))

    if not files:
        print("(empty)")
        continue

    for path in files:
        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
            print(
                f"- {data.get('name', path.stem)}"
                f" | success_count="
                f"{data.get('success_count','-')}"
            )
        except Exception:
            print(f"- {path.name}")
