import re
from collections.abc import Iterable

from app.models.product import ProductCandidate
from app.services.color_normalizer import (
    EXACT_VARIANT,
    extract_color_identity,
)
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
            r"cloud\s+white|frost|фрост\w*|white|бел\w*)\b",
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
            r"\b(?:hazel|lemongrass|forest\s+hazel|jade|mint|sage|green|"
            r"нефрит\w*|лемонграсс\w*|лесн\w*\s+орех\w*|"
            r"мятн\w*|зелен\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "blue",
        re.compile(
            r"\b(?:bay|blue|navy|indigo|индиго\w*|голуб\w*|син\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "pink",
        re.compile(
            r"\b(?:peony|rose|berry|pink|ягод\w*|розов\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "gray",
        re.compile(
            r"\b(?:graphite|moonstone|mist|fog|gray|grey|"
            r"лунн\w*\s+камень|туман\w*|сер(?:ый|ая|ое|ые)|"
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
            r"\b(?:lavender|lilac|purple|лаванд\w*|сирен\w*|"
            r"лилов\w*|фиолет\w*)\b",
            re.IGNORECASE,
        ),
    ),
)
_COLOR_DESCRIPTOR_PATTERN = re.compile(
    r"^(?:"
    r"natural|desert|space|cloud|mist|sky|rose|cosmic|matte|"
    r"storm|glacier|phantom|awesome|bora|icy|deep|dark|light|"
    r"black|white|blue|green|gold|silver|titanium|graphite|"
    r"природн\w*|пустынн\w*|космическ\w*|матов\w*|"
    r"темн\w*|светл\w*|глубок\w*|ледян\w*|"
    r"черн\w*|бел\w*|син\w*|зелен\w*|золот\w*|"
    r"серебр\w*|титан\w*|графитов\w*"
    r")$",
    re.IGNORECASE,
)


def requested_color_key(value: str | None) -> str | None:
    """Определяет нормализованный цвет карточки или пользовательского ввода."""

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
    """Разделяет разные exact-variant, сохраняя общий цвет как fallback."""

    requested_identity = extract_color_identity(requested_title)
    candidate_identity = extract_color_identity(candidate_title)

    if (
        requested_identity is not None
        and requested_identity.confidence == EXACT_VARIANT
    ):
        if candidate_identity is None:
            return True
        if candidate_identity.confidence == EXACT_VARIANT:
            return requested_identity.variant != candidate_identity.variant

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
    normalized = re.sub(
        r"(?<!\d)\d{1,4}\s*"
        r"(?:gb|tb|mb|гб|тб|мб)?\s*/\s*"
        r"\d{1,4}\s*(?:gb|tb|mb|гб|тб|мб)?(?!\w)",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b\d+\s*(?:gb|tb|mb|гб|тб|мб)\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )

    return set(
        re.findall(
            r"(?<![a-zа-я0-9])\d{1,2}(?![a-zа-я0-9])",
            normalized,
        )
    )


def _search_generation_numbers(value: str) -> set[str]:
    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(
        r"(?<!\d)\d{1,4}\s*"
        r"(?:gb|tb|mb|гб|тб|мб)?\s*/\s*"
        r"\d{1,4}\s*(?:gb|tb|mb|гб|тб|мб)?(?!\w)",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b\d+\s*(?:gb|tb|mb|гб|тб|мб)\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    numbers = significant_model_numbers(value)
    numbers.update(
        re.findall(
            r"(?<![a-zа-я0-9])(\d{1,2})(?=[a-zа-я]\b)",
            normalized,
        )
    )
    return numbers


def filter_products_by_query_generation(
    products: Iterable[ProductCandidate],
    query: str,
) -> list[ProductCandidate]:
    """Оставляет точное поколение в первом экране поиска."""

    product_list = list(products)
    requested_numbers = _search_generation_numbers(query)
    if not requested_numbers:
        return product_list

    matching = [
        product
        for product in product_list
        if requested_numbers.issubset(
            _search_generation_numbers(product.title)
        )
    ]
    return matching or product_list


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


def color_neutral_title(title: str) -> str:
    """Удаляет цвет, сохраняя модель, память, версию и ревизию."""

    return _strip_color_suffix(title)


def model_variant_title(title: str) -> str:
    """Возвращает модель без памяти и цветового оформления."""

    result = color_neutral_title(title)
    normalized = base_product_title(result)
    return normalized or title


def group_model_variants(
    products: Iterable[ProductCandidate],
) -> list[ProductVariantGroup]:
    """Объединяет цвета и память одной физической модели."""

    product_list = list(products)
    contextual_stems = _contextual_parenthetical_color_stems(product_list)
    groups: dict[str, list[ProductCandidate]] = {}
    titles: dict[str, str] = {}

    for product in product_list:
        source_title = product.title
        contextual = _parenthetical_stem(source_title)
        if (
            contextual is not None
            and _model_key(model_variant_title(contextual)) in contextual_stems
        ):
            source_title = contextual
        title = model_variant_title(source_title)
        key = _model_key(title)
        groups.setdefault(key, []).append(product)
        titles.setdefault(key, title)

    return [
        ProductVariantGroup(
            title=titles[key],
            products=group_products,
        )
        for key, group_products in groups.items()
    ]


def _model_key(title: str) -> str:
    return re.sub(
        r"[^a-zа-я0-9]+",
        " ",
        title.casefold().replace("ё", "е"),
    ).strip()


_TECHNICAL_PARENTHETICAL = re.compile(
    r"^(?:wi[- ]?fi|lte|5g|4g|global|china|cn|eu|us|usa|"
    r"dual\s*sim|single\s*sim|esim|refurbished|renewed|"
    r"уценк\w*|восстановлен\w*|без\s+дисковода)$",
    re.IGNORECASE,
)


def _parenthetical_stem(title: str) -> str | None:
    match = re.search(r"\s*\(([^()]*)\)\s*$", title)
    if match is None:
        return None
    suffix = " ".join(match.group(1).split())
    if (
        not suffix
        or len(suffix) > 40
        or any(character.isdigit() for character in suffix)
        or _TECHNICAL_PARENTHETICAL.fullmatch(suffix) is not None
    ):
        return None
    return title[: match.start()].strip(" -/,")


def _contextual_parenthetical_color_stems(
    products: list[ProductCandidate],
) -> set[str]:
    variants: dict[str, set[str]] = {}
    bare_keys = {_model_key(model_variant_title(product.title)) for product in products}
    for product in products:
        stem = _parenthetical_stem(product.title)
        if stem is None:
            continue
        suffix_match = re.search(r"\(([^()]*)\)\s*$", product.title)
        if suffix_match is None:
            continue
        key = _model_key(model_variant_title(stem))
        variants.setdefault(key, set()).add(suffix_match.group(1).casefold())
    return {
        key
        for key, suffixes in variants.items()
        if len(suffixes) >= 2 or key in bare_keys
    }


def selected_color_label(title: str) -> str | None:
    """Возвращает понятную подпись цвета для любой категории товара."""

    known_label = display_color(title)
    if known_label is not None:
        return known_label

    trailing = re.search(r"\(([^()]*)\)\s*$", title)
    if (
        trailing is not None
        and requested_color_key(trailing.group(1)) is not None
    ):
        return _display_suffix(trailing.group(1))

    suffix = _color_suffix(title)
    if suffix is not None:
        return _display_suffix(suffix)

    for _, pattern in _COLOR_ALIAS_PATTERNS:
        match = pattern.search(title)
        if match is not None:
            return _display_suffix(match.group(0))
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
    result = _strip_color_suffix(title)
    result = re.sub(r"[^a-zа-я0-9]+", " ", result.casefold())
    return " ".join(result.split())


def _strip_color_suffix(title: str) -> str:
    """Удаляет только цветовой суффикс, не трогая слова внутри модели."""

    result = " ".join(title.split()).strip()
    trailing = re.search(r"\s*\(([^()]*)\)\s*$", result)
    if (
        trailing is not None
        and requested_color_key(trailing.group(1)) is not None
    ):
        return result[:trailing.start()].strip(" -/,")

    suffix = _color_suffix(result)
    if suffix is None:
        return result

    prefix = result[: len(result) - len(suffix)].strip(" -/,")
    return prefix or result


def _color_suffix(title: str) -> str | None:
    """Находит конечную цветовую фразу, не принимая Pro/Plus за цвет."""

    full_color = requested_color_key(title)
    if full_color is None:
        return None

    tokens = title.split()
    if not tokens:
        return None

    last_token = tokens[-1].strip("()[]{}.,;:-_/ ")
    if not last_token or requested_color_key(last_token) is None:
        # Цвет должен завершать название. Иначе слова после цвета могут быть
        # состоянием товара, комплектом или иной значимой модификацией.
        return None

    max_width = min(4, len(tokens) - 1)
    for width in range(1, max_width + 1):
        raw_suffix = " ".join(tokens[-width:])
        suffix = raw_suffix.strip("()[]{}.,;:-_/ ")
        if not suffix or any(character.isdigit() for character in suffix):
            continue
        if requested_color_key(suffix) != full_color:
            continue

        start = len(tokens) - width
        while start > 0:
            previous = tokens[start - 1].strip("()[]{}.,;:-_/ ")
            if (
                not previous
                or any(character.isdigit() for character in previous)
                or _COLOR_DESCRIPTOR_PATTERN.fullmatch(previous) is None
            ):
                break
            expanded = " ".join(tokens[start - 1:])
            if requested_color_key(expanded) != full_color:
                break
            start -= 1
        return " ".join(tokens[start:])
    return None


def _display_suffix(value: str) -> str:
    normalized = " ".join(value.strip("()[]{}.,;:-_/ ").split())
    return normalized[:1].upper() + normalized[1:]
