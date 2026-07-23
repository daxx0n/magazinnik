from pathlib import Path


path = Path(__file__).resolve().parents[1] / "app/services/model_selection.py"
text = path.read_text()
old = '''_LIGHT_COLOR_WORDS = (
    "black|blue|green|gray|grey|pink|purple|red|white|yellow|"
    "gold|golden|silver|черн\\w*|син\\w*|голуб\\w*|зелен\\w*|"
    "сер\\w*|розов\\w*|фиолет\\w*|красн\\w*|бел\\w*|желт\\w*|"
    "золот\\w*|серебр\\w*"
)'''
new = '''_LIGHT_COLOR_WORDS = (
    r"black|blue|green|gray|grey|pink|purple|red|white|yellow|"
    r"gold|golden|silver|черн\\w*|син\\w*|голуб\\w*|зелен\\w*|"
    r"сер\\w*|розов\\w*|фиолет\\w*|красн\\w*|бел\\w*|желт\\w*|"
    r"золот\\w*|серебр\\w*"
)'''
if old not in text:
    raise RuntimeError("Light-color regex block not found")
path.write_text(text.replace(old, new, 1))
