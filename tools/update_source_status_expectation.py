from pathlib import Path

path = Path("tests/test_source_statuses.py")
text = path.read_text(encoding="utf-8")
old = '            requested_title="Bosch HBA534EB3",\n'
new = '            requested_title=canonical,\n'
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise RuntimeError("expected assertion not found")
path.write_text(text, encoding="utf-8")
