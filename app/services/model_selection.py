import re
from collections.abc import Iterable

from app.models.product import ProductCandidate
from app.services.color_normalizer import (
    color_identities_match,
    extract_color_identity,
    extract_color_phrase,
)
from app.services.product_variants import (
    ProductVariantGroup,
    base_product_title,
    display_color,
)


def requested_color_key(value: str | None) -> str | None:
    """Returns one shared exact-variant or base-family color key."""

    identity = extract_color_identity(value)
    return identity.key if identity is not None else None


def explicit_color_mismatch(
    requested_title: str | None,
    candidate_title: str,
) -> bool:
    """Strictly checks an explicitly selected trailing color variant."""

    requested_color = extract_color_identity(requested_title)
    if requested_color is None:
        return False

    candidate_color = extract_color_identity(candidate_title)
    if candidate_color is None:
        return True
    return not color_identities_match(requested_color, candidate_color)


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

    phrase = extract_color_phrase(title)
    return _display_suffix(phrase) if phrase is not None else None


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
        and extract_color_identity(trailing.group(1)) is not None
    ):
        return result[:trailing.start()].strip(" -/,")

    suffix = _color_suffix(result)
    if suffix is None:
        return result

    prefix = result[: len(result) - len(suffix)].strip(" -/,")
    return prefix or result


def _color_suffix(title: str) -> str | None:
    """Находит только явную конечную цветовую фразу."""

    return extract_color_phrase(title)


def _display_suffix(value: str) -> str:
    normalized = " ".join(value.strip("()[]{}.,;:-_/ ").split())
    return normalized[:1].upper() + normalized[1:]
