from pathlib import Path

path = Path("tests/test_source_statuses.py")
text = path.read_text(encoding="utf-8")
old = '            "ol:model-19",\n'
new = '            "olg:search:19",\n'
if old not in text:
    raise RuntimeError("Expected pagination assertion not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
