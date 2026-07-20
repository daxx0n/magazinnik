from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f"Missing target: {label}")


def patch_search_handler() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text(encoding="utf-8")
    broken = '        f"📱 {group.title}\n\n"\n'
    fixed = '        f"📱 {group.title}\\n\\n"\n'
    text = replace_once(text, broken, fixed, "variant prompt")
    path.write_text(text, encoding="utf-8")


def patch_model_selection() -> None:
    path = ROOT / "app/services/model_selection.py"
    text = path.read_text(encoding="utf-8")
    marker = """def model_variant_title(title: str) -> str:\n    \"\"\"Возвращает модель без памяти и цветового оформления.\"\"\"\n\n    result = _strip_color_suffix(title)\n    normalized = base_product_title(result)\n    return normalized or title\n\n\n"""
    replacement = """def color_neutral_title(title: str) -> str:\n    \"\"\"Удаляет цвет, сохраняя модель, память, версию и ревизию.\"\"\"\n\n    return _strip_color_suffix(title)\n\n\ndef model_variant_title(title: str) -> str:\n    \"\"\"Возвращает модель без памяти и цветового оформления.\"\"\"\n\n    result = color_neutral_title(title)\n    normalized = base_product_title(result)\n    return normalized or title\n\n\n"""
    text = replace_once(text, marker, replacement, "color-neutral helper")
    path.write_text(text, encoding="utf-8")


def patch_catalog_first_search() -> None:
    path = ROOT / "app/services/catalog_first_search.py"
    text = path.read_text(encoding="utf-8")
    old_import = """from app.services.model_selection import (\n    explicit_color_mismatch,\n    generation_mismatch,\n    requested_color_key,\n)\n"""
    new_import = """from app.services.model_selection import (\n    color_neutral_title,\n    explicit_color_mismatch,\n    generation_mismatch,\n    requested_color_key,\n)\n"""
    text = replace_once(text, old_import, new_import, "catalog selection import")

    old_block = """        reference_color = requested_color_key(reference_title)\n        candidate_color = requested_color_key(candidate_title)\n        if explicit_color_mismatch(\n            requested_title=reference_title,\n            candidate_title=candidate_title,\n        ):\n            return \"color_unknown\" if candidate_color is None else \"color\"\n\n        reason = PriceService._model_mismatch_reason(\n            canonical_title=canonical_title,\n            candidate_title=candidate_title,\n            requested_title=reference_title,\n        )\n        if (\n            reason == \"color\"\n            and reference_color is not None\n            and candidate_color == reference_color\n        ):\n            return None\n        return reason\n"""
    new_block = """        reference_color = requested_color_key(reference_title)\n        candidate_color = requested_color_key(candidate_title)\n        reason = PriceService._model_mismatch_reason(\n            canonical_title=color_neutral_title(canonical_title),\n            candidate_title=color_neutral_title(candidate_title),\n            requested_title=color_neutral_title(reference_title),\n        )\n        if reason is not None:\n            return reason\n\n        if explicit_color_mismatch(\n            requested_title=reference_title,\n            candidate_title=candidate_title,\n        ):\n            return \"color_unknown\" if candidate_color is None else \"color\"\n\n        if (\n            reference_color is not None\n            and candidate_color == reference_color\n        ):\n            return None\n        return None\n"""
    text = replace_once(text, old_block, new_block, "variant mismatch priority")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_search_handler()
    patch_model_selection()
    patch_catalog_first_search()


if __name__ == "__main__":
    main()
