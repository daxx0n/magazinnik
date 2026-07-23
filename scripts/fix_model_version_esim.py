from pathlib import Path


path = Path(__file__).resolve().parents[1] / "app/services/model_selection.py"
text = path.read_text()
old = '''    normalized = color_neutral_title(value).casefold().replace("ё", "е")
    normalized = re.sub(r"\\bmini[\\s-]*led\\b", " ", normalized)
'''
new = '''    normalized = color_neutral_title(value).casefold().replace("ё", "е")
    normalized = re.sub(r"\\be[\\s-]*sim\\b", " ", normalized)
    normalized = re.sub(r"\\bmini[\\s-]*led\\b", " ", normalized)
'''
if old not in text:
    raise RuntimeError("Model-version normalization marker not found")
path.write_text(text.replace(old, new, 1))
