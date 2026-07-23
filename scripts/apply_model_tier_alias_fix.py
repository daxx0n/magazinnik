from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def patch_model_selection() -> None:
    path = ROOT / "app/services/model_selection.py"
    text = path.read_text()
    if "def model_version_signature(" in text:
        return

    marker = "\n\ndef requested_color_key("
    addition = '''\n\n_MODEL_VERSION_ALIASES = {
    "pro": "pro",
    "про": "pro",
    "max": "max",
    "макс": "max",
    "plus": "plus",
    "плюс": "plus",
    "ultra": "ultra",
    "ультра": "ultra",
    "air": "air",
    "эйр": "air",
    "mini": "mini",
    "мини": "mini",
    "lite": "lite",
    "light": "lite",
    "лайт": "lite",
    "xl": "xl",
    "fe": "fe",
    "e": "e",
}
_LIGHT_COLOR_WORDS = (
    "black|blue|green|gray|grey|pink|purple|red|white|yellow|"
    "gold|golden|silver|черн\\w*|син\\w*|голуб\\w*|зелен\\w*|"
    "сер\\w*|розов\\w*|фиолет\\w*|красн\\w*|бел\\w*|желт\\w*|"
    "золот\\w*|серебр\\w*"
)


def model_version_signature(value: str | None) -> frozenset[str]:
    """Returns canonical material model-tier markers across languages.

    Examples: Lite/Light/Лайт map to ``lite`` and Mini/Мини map to
    ``mini``. Display technology (MiniLED) and color phrases such as
    ``Light Blue`` are excluded so they do not become model variants.
    """

    if not value:
        return frozenset()

    normalized = color_neutral_title(value).casefold().replace("ё", "е")
    normalized = re.sub(r"\\bmini[\\s-]*led\\b", " ", normalized)
    normalized = re.sub(
        rf"\\blight\\s+(?:{_LIGHT_COLOR_WORDS})\\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    tokens = re.findall(r"[a-zа-я]+|\\d+", normalized)
    return frozenset(
        _MODEL_VERSION_ALIASES[token]
        for token in tokens
        if token in _MODEL_VERSION_ALIASES
    )
'''
    if marker not in text:
        raise RuntimeError("requested_color_key marker not found")
    path.write_text(text.replace(marker, addition + marker, 1))


def patch_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text()

    import_marker = "from app.services.model_code_matching import technical_model_code_words\n"
    import_replacement = (
        import_marker
        + "from app.services.model_selection import model_version_signature\n"
    )
    if "from app.services.model_selection import model_version_signature" not in text:
        if import_marker not in text:
            raise RuntimeError("model_code_matching import marker not found")
        text = text.replace(import_marker, import_replacement, 1)

    old_function = '''        def version_tokens(value: str) -> set[str]:
            value = re.sub(
                r"\\be\\s+sim\\b",
                " ",
                value,
            )
            tokens = set(
                re.findall(
                    r"[a-zа-я]+|\\d+",
                    value,
                )
            )
            markers = {
                "pro",
                "max",
                "plus",
                "ultra",
                "air",
                "mini",
                "lite",
                "xl",
                "fe",
                "e",
            }
            return tokens & markers

'''
    if old_function in text:
        text = text.replace(old_function, "", 1)
    elif "def version_tokens(" in text:
        raise RuntimeError("Unexpected version_tokens implementation")

    text = text.replace(
        "            version_tokens(canonical)\n            != version_tokens(candidate)",
        "            model_version_signature(canonical)\n            != model_version_signature(candidate)",
        1,
    )
    if "version_tokens(canonical)" in text:
        raise RuntimeError("Legacy version token call remains")

    path.write_text(text)


def main() -> None:
    patch_model_selection()
    patch_price_service()


if __name__ == "__main__":
    main()
