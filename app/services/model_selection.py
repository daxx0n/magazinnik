import re
from collections.abc import Iterable

from app.models.product import ProductCandidate
from app.services.product_variants import (
    ProductVariantGroup,
    base_product_title,
    display_color,
    extract_color,
    extract_color_key,
    extract_memory,
)


_COLOR_ALIAS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "white",
        re.compile(
            r"\b(?:snow|снег\w*|porcelain|фарфор\w*|"
            r"cloud\s+white|white|бел\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "black",
        re.compile(
            r"\b(?:obsidian|обсидиан\w*|charcoal|"
            r"space\s+black|black|черн\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "green",
        re.compile(
            r"\b(?:hazel|lemongrass|mint|sage|green|"
            r"мятн\w*|зелен\w*)\b",
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
            r"\b(?:graphite|gray|grey|сер(?:ый|ая|ое|ые)|"
            r"графитов\w*)\b",
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
            r"\b(?:lavender|lilac|purple|сирен\w*|"
            r"лилов\w*|фиолет\w*)\b",
            re.IGNORECASE,
        ),
    ),
)


def requested_color_key(value: str | None) -> str | None:
    """Определяет цвет, явно указанный пользователем или карточкой."""

    if not value:
        return None

    known_key = extract_color_key(value)
    if known_key is not None:
        return known_key

    for color_key, pattern in _COLOR_ALIAS_PATTERNS:
        if pattern.search(value):
            return color_key
    return None


def explicit_color_mismatch(
    requested_title: str | None,
    candidate_title: str,
) -> bool:
    """Строго проверяет цвет после выбора конечной модификации."""

    requested_color = requested_color_key(requested_title)
    candidate_color = requested_color_key(candidate_title)
    return bool(
        requested_color is not None
        and candidate_color != requested_color
    )


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
        for number in re.findall(
            r"(?<![a-zа-я0-9])\d{1,2}(?![a-zа-я0-9])",
            normalized,
        )
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


def model_variant_title(title: str) -> str:
    """Возвращает модель без памяти и цветового оформления."""

    result = title
    trailing = re.search(r"\s*\(([^()]*)\)\s*$", result)

    if (
        trailing is not None
        and requested_color_key(trailing.group(1)) is not None
    ):
        result = result[:trailing.start()].strip()
    elif requested_color_key(result) is not None:
        for _, pattern in _COLOR_ALIAS_PATTERNS:
            result = pattern.sub(" ", result)

    normalized = base_product_title(result)
    return normalized or title


def group_model_variants(
    products: Iterable[ProductCandidate],
) -> list[ProductVariantGroup]:
    """Объединяет цвета и память одной физической модели."""

    groups: dict[str, list[ProductCandidate]] = {}
    titles: dict[str, str] = {}

    for product in products:
        title = model_variant_title(product.title)
        key = re.sub(
            r"[^a-zа-я0-9]+",
            " ",
            title.casefold().replace("ё", "е"),
        ).strip()
        groups.setdefault(key, []).append(product)
        titles.setdefault(key, title)

    return [
        ProductVariantGroup(
            title=titles[key],
            products=group_products,
        )
        for key, group_products in groups.items()
    ]


def selected_color_label(title: str) -> str | None:
    """Возвращает понятную подпись цвета, включая маркетинговые алиасы."""

    known_label = display_color(title)
    if known_label is not None:
        return known_label

    trailing = re.search(r"\(([^()]*)\)\s*$", title)
    if (
        trailing is not None
        and requested_color_key(trailing.group(1)) is not None
    ):
        value = " ".join(trailing.group(1).split())
        return value[:1].upper() + value[1:]

    for _, pattern in _COLOR_ALIAS_PATTERNS:
        match = pattern.search(title)
        if match is not None:
            value = " ".join(match.group(0).split())
            return value[:1].upper() + value[1:]
    return None


def collapse_color_variants(
    products: Iterable[ProductCandidate],
    query: str,
) -> list[ProductCandidate]:
    """Совместимый helper; UI теперь группирует цвета после выбора модели."""

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
    trailing = re.search(r"\(([^()]*)\)\s*$", result)
    if (
        explicit_color is not None
        or (
            trailing is not None
            and requested_color_key(trailing.group(1)) is not None
        )
    ):
        result = re.sub(r"\s*\([^()]*\)\s*$", "", result)

    for _, pattern in _COLOR_ALIAS_PATTERNS:
        result = pattern.sub(" ", result)

    result = re.sub(r"[^a-zа-я0-9]+", " ", result.casefold())
    return " ".join(result.split())
