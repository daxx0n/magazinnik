from pathlib import Path


path = Path(__file__).resolve().parents[1] / "tests/test_source_statuses.py"
text = path.read_text()
text = text.replace(
    '"📱 Apple iPhone 17 512GB (Mist Blue)"',
    '"🏷️ Apple iPhone 17 512GB (Mist Blue)"',
)
path.write_text(text)
