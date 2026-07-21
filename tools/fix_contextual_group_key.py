from pathlib import Path

path = Path("app/services/model_selection.py")
text = path.read_text(encoding="utf-8")
old = "if contextual is not None and _model_key(contextual) in contextual_stems:"
new = (
    "if (\n"
    "            contextual is not None\n"
    "            and _model_key(model_variant_title(contextual)) in contextual_stems\n"
    "        ):"
)
if old not in text:
    raise RuntimeError("contextual key condition not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
