import re
from collections.abc import Iterable

from app.models.product import ProductCandidate
from app.services.product_variants import (
    extract_color,
    extract_color_key,
    extract_memory,
)


_COLOR_ALIAS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "white",
        re.compile(
            r"\b(?:snow|снег|porcelain|cloud\s+white|white|бел\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "black",
        re.compile(
            r"\b(?:obsidian|charcoal|space\s+black|black|черн\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "green",
        re.compile(
            r"\b(?:hazel|lemongrass|mint|sage|green|мятн\w*|зелен\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "blue",
        re.compile(
            r"\b(?:bay|blue|navy|голуб\w*|син\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "pink",
        re.compile(
            r"\b(?:peony|rose|pink|розов\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "gray",
        re.compile(
            r"\b(?:graphite|gray|grey|сер(?:ый|ая|ое|ые)|графитов\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "yellow",
        re.compile(r"\b(?:yellow|желт\w*)\b", re.IGNORECASE),
    ),
    (
        "red",
        re.compile(r"\b(?:red|красн\w*)\b", re.IGNORECASE),
    ),
    (
        "purple",
        re.compile(
            r"\b(?:lavender|lilac|purple|сирен\w*|лилов\w*|фиолет\w*)\b",
            re.IGNORECASE,
        ),
    ),
)


def requested_color_key(value: str | None) -> str | None:
    """Определяет цвет, явно указанный пользователем."""

    if not value:
        return None

    known_key = extract_color_key(value)
    if known_key is not None:
        return known_key

    for color_key, pattern in _COLOR_ALIAS_PATTERNS:
        if pattern.search(value):
            return color_key
    return None


def significant_model_numbers(value: str) -> set[str]:
    """Извлекает номер поколения, исключая RAM и накопитель."""

    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(
        r"\bps\s*([45])\b",
        r"playstation \1",
        normalized,
    )
    memory = extract_memory(value)
    memory_amounts = (
        set(re.findall(r"\d+", memory))
        if memory is not None
        else set()
    )

    return {
        number
        for number in re.findall(r"(?<![a-zа-я0-9])\d{1,2}(?![a-zа-я0-9])", normalized)
        if number not in memory_amounts
    }


def generation_mismatch(
    canonical_title: str,
    candidate_title: str,
    requested_title: str | None = None,
) -> bool:
    """Не позволяет памяти кандидата маскировать другое поколение."""

    reference = requested_title or canonical_title
    reference_numbers = significant_model_numbers(reference)
    candidate_numbers = significant_model_numbers(candidate_title)

    return bool(
        reference_numbers
        and candidate_numbers
        and not reference_numbers.issubset(candidate_numbers)
    )


def collapse_color_variants(
    products: Iterable[ProductCandidate],
    query: str,
) -> list[ProductCandidate]:
    """Оставляет одну карточку модели/памяти при запросе без цвета."""

    product_list = list(products)
    if requested_color_key(query) is not None:
        return product_list

    selected: dict[str, ProductCandidate] = {}
    for product in product_list:
        key = _color_agnostic_title(product.title)
        selected.setdefault(key, product)
    return list(selected.values())


def _color_agnostic_title(title: str) -> str:
    result = title
    explicit_color = extract_color(result)
    if explicit_color is not None or _parenthesized_color(result):
        result = re.sub(r"\s*\([^()]*\)\s*$", "", result)

    for _, pattern in _COLOR_ALIAS_PATTERNS:
        result = pattern.sub(" ", result)

    result = re.sub(r"[^a-zа-я0-9]+", " ", result.casefold())
    return " ".join(result.split())


def _parenthesized_color(title: str) -> bool:
    match = re.search(r"\(([^()]*)\)\s*$", title)
    if match is None:
        return False
    value = match.group(1)
    return any(pattern.search(value) for _, pattern in _COLOR_ALIAS_PATTERNS)
