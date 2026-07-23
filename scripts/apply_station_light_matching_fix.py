from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def patch_model_code_matching() -> None:
    path = ROOT / "app/services/model_code_matching.py"
    text = path.read_text()
    if "def technical_model_code_words(" in text:
        return

    marker = "\n\ndef short_marketing_model_codes("
    addition = '''\n\ndef technical_model_code_words(value: str) -> set[str]:
    """Returns alphabetic fragments that belong to separated model codes.

    Store titles often put a code such as YNDX-00028 or GFY-LX1 before or
    immediately after the real brand. Those fragments must not be interpreted
    as a manufacturer name during brand matching.
    """

    _, parts = _separated_long_codes(_normalize(value))
    return {part for part in parts if part.isalpha()}
'''
    if marker not in text:
        raise RuntimeError("short_marketing_model_codes marker not found")
    path.write_text(text.replace(marker, addition + marker, 1))


def patch_variant_matching() -> None:
    path = ROOT / "app/services/variant_matching.py"
    text = path.read_text()

    if "_DISPLAY_CONFIGURATION_PATTERNS" not in text:
        marker = "\n\n_VARIANT_REMOVERS = ("
        addition = '''\n\n_DISPLAY_CONFIGURATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "without_display",
        re.compile(
            r"\\b(?:без\\s+(?:час\\w*|диспле\\w*|экран\\w*)|"
            r"without\\s+(?:clock|display|screen))\\b",
            re.I,
        ),
    ),
    (
        "with_display",
        re.compile(
            r"\\b(?:(?:с|со)\\s+(?:час\\w*|диспле\\w*|экран\\w*)|"
            r"with\\s+(?:clock|display|screen))\\b",
            re.I,
        ),
    ),
)
'''
        if marker not in text:
            raise RuntimeError("variant remover marker not found")
        text = text.replace(marker, addition + marker, 1)

    if "def clock_display_configuration(" not in text:
        marker = "\n\ndef product_condition("
        addition = '''\n\ndef clock_display_configuration(value: str | None) -> str | None:
    """Returns an explicit with/without clock or display configuration."""

    if not value:
        return None
    for configuration, pattern in _DISPLAY_CONFIGURATION_PATTERNS:
        if pattern.search(value):
            return configuration
    return None
'''
        if marker not in text:
            raise RuntimeError("product_condition marker not found")
        text = text.replace(marker, addition + marker, 1)

    mismatch_marker = '''    requested_region = explicit_region(requested_title)
    candidate_region = explicit_region(candidate_title)
'''
    if "requested_display = clock_display_configuration" not in text:
        mismatch_block = '''    requested_display = clock_display_configuration(requested_title)
    candidate_display = clock_display_configuration(candidate_title)
    if (
        requested_display != candidate_display
        and (requested_display is not None or candidate_display is not None)
    ):
        return "configuration"

'''
        if mismatch_marker not in text:
            raise RuntimeError("region mismatch marker not found")
        text = text.replace(mismatch_marker, mismatch_block + mismatch_marker, 1)

    neutral_marker = '''    for _, pattern in _REGION_PATTERNS:
        result = pattern.sub(" ", result)
    for pattern in _VARIANT_REMOVERS:
'''
    if "for _, pattern in _DISPLAY_CONFIGURATION_PATTERNS" not in text.split("def neutralize_variant_markers", 1)[1]:
        neutral_block = '''    for _, pattern in _REGION_PATTERNS:
        result = pattern.sub(" ", result)
    for _, pattern in _DISPLAY_CONFIGURATION_PATTERNS:
        result = pattern.sub(" ", result)
    for pattern in _VARIANT_REMOVERS:
'''
        if neutral_marker not in text:
            raise RuntimeError("neutralization marker not found")
        text = text.replace(neutral_marker, neutral_block, 1)

    path.write_text(text)


def patch_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text()

    if "technical_model_code_words" not in text.split("class PriceService", 1)[0]:
        marker = "from app.services.catalog_service import CatalogService\n"
        replacement = (
            marker
            + "from app.services.model_code_matching import "
            + "technical_model_code_words\n"
        )
        if marker not in text:
            raise RuntimeError("catalog service import marker not found")
        text = text.replace(marker, replacement, 1)

    generic_marker = '''        canonical_brand = next(
'''
    if "canonical_code_words = technical_model_code_words" not in text:
        code_words = '''        canonical_code_words = technical_model_code_words(
            canonical_title
        )
        candidate_code_words = technical_model_code_words(
            candidate_title
        )

'''
        if generic_marker not in text:
            raise RuntimeError("canonical brand marker not found")
        text = text.replace(generic_marker, code_words + generic_marker, 1)

    canonical_filter = '''                    and token
                    not in generic_title_words
'''
    canonical_replacement = '''                    and token
                    not in generic_title_words
                    and token not in canonical_code_words
'''
    if canonical_replacement not in text:
        if canonical_filter not in text:
            raise RuntimeError("canonical latin brand filter not found")
        text = text.replace(canonical_filter, canonical_replacement, 1)

    canonical_fallback_filter = '''                        token.isalpha()
                        and token not in generic_title_words
'''
    canonical_fallback_replacement = '''                        token.isalpha()
                        and token not in generic_title_words
                        and token not in canonical_code_words
'''
    if canonical_fallback_replacement not in text:
        if canonical_fallback_filter not in text:
            raise RuntimeError("canonical fallback brand filter not found")
        text = text.replace(
            canonical_fallback_filter,
            canonical_fallback_replacement,
            1,
        )

    candidate_filter = '''                    re.fullmatch(r"[a-z]+", token)
                    and token not in generic_title_words
'''
    candidate_replacement = '''                    re.fullmatch(r"[a-z]+", token)
                    and token not in generic_title_words
                    and token not in candidate_code_words
'''
    if candidate_replacement not in text:
        if candidate_filter not in text:
            raise RuntimeError("candidate latin brand filter not found")
        text = text.replace(candidate_filter, candidate_replacement, 1)

    candidate_fallback_filter = '''                        token.isalpha()
                        and token not in generic_title_words
'''
    candidate_fallback_replacement = '''                        token.isalpha()
                        and token not in generic_title_words
                        and token not in candidate_code_words
'''
    if text.count(candidate_fallback_replacement) < 1:
        # The canonical fallback was already replaced, so replace the next
        # remaining occurrence for the candidate branch.
        if candidate_fallback_filter not in text:
            raise RuntimeError("candidate fallback brand filter not found")
        text = text.replace(
            candidate_fallback_filter,
            candidate_fallback_replacement,
            1,
        )
    elif text.count(candidate_fallback_replacement) == 1:
        if candidate_fallback_filter not in text:
            raise RuntimeError("candidate fallback brand filter not found")
        text = text.replace(
            candidate_fallback_filter,
            candidate_fallback_replacement,
            1,
        )

    alias_marker = '''            {"playstation", "sony"},
            {"poco", "redmi", "xiaomi"},
'''
    alias_replacement = '''            {"playstation", "sony"},
            {"poco", "redmi", "xiaomi"},
            {"yandex", "яндекс"},
'''
    if alias_replacement not in text:
        if alias_marker not in text:
            raise RuntimeError("brand alias marker not found")
        text = text.replace(alias_marker, alias_replacement, 1)

    path.write_text(text)


def main() -> None:
    patch_model_code_matching()
    patch_variant_matching()
    patch_price_service()


if __name__ == "__main__":
    main()
