from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f"Missing target: {label}")


def patch_model_numbers() -> None:
    path = ROOT / "app/services/model_selection.py"
    text = path.read_text(encoding="utf-8")
    old = '''    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(
        r"\\bps\\s*([45])\\b",
        r"playstation \\1",
        normalized,
    )
    memory = extract_memory(value)
    memory_amounts = (
        set(re.findall(r"\\d+", memory))
        if memory is not None
        else set()
    )

    return {
        number
        for number in re.findall(
            r"(?<![a-zа-я0-9])\\d{1,2}(?![a-zа-я0-9])",
            normalized,
        )
        if number not in memory_amounts
    }
'''
    new = '''    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(
        r"\\bps\\s*([45])\\b",
        r"playstation \\1",
        normalized,
    )
    normalized = re.sub(
        r"(?<!\\d)\\d{1,4}\\s*"
        r"(?:gb|tb|mb|гб|тб|мб)?\\s*/\\s*"
        r"\\d{1,4}\\s*(?:gb|tb|mb|гб|тб|мб)?(?!\\w)",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\\b\\d+\\s*(?:gb|tb|mb|гб|тб|мб)\\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )

    return set(
        re.findall(
            r"(?<![a-zа-я0-9])\\d{1,2}(?![a-zа-я0-9])",
            normalized,
        )
    )
'''
    text = replace_once(text, old, new, "memory span model numbers")
    path.write_text(text, encoding="utf-8")


def patch_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text(encoding="utf-8")
    old = '''        # После выбора карточки именно полное название варианта,
        # а не исходный широкий запрос, является эталоном мэтчинга.
        requested_query = canonical_title
'''
    new = '''        original_query = self._onliner_queries.get(
            product_key,
            canonical_title,
        )
        # После выбора карточки полное название варианта используется
        # только как эталон мэтчинга. Исходный запрос сохраняется для UX.
        matching_reference = canonical_title
'''
    text = replace_once(text, old, new, "query and matching reference")
    text = text.replace(
        "requested_title=requested_query",
        "requested_title=matching_reference",
    )
    text = text.replace(
        "requested_title=(\n                                requested_query\n                            )",
        "requested_title=(\n                                matching_reference\n                            )",
    )
    text = replace_once(
        text,
        "            query=requested_query,\n",
        "            query=original_query,\n",
        "comparison query",
    )
    if "requested_query" in text:
        raise RuntimeError("Unresolved requested_query reference")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_model_numbers()
    patch_price_service()


if __name__ == "__main__":
    main()
