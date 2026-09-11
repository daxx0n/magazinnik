"""Presentation-only normalization for model and color selection screens.

These helpers intentionally do not change the production offer matcher. They
only control how search results are grouped and deduplicated in Telegram UI.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace

from app.models.product import ProductCandidate
from app.services.color_normalizer import EXACT_VARIANT, UNKNOWN, extract_color_identity, extract_color_phrase
from app.services.sim_selection import without_sim
from app.services.model_selection import (
    group_model_variants,
    requested_color_key,
    selected_color_label as legacy_color_label,
)
from app.services.product_variants import ProductVariantGroup


_ISAI_BLUE_SUFFIX = re.compile(r"\s+isai[-\s]+blue\s*$", re.IGNORECASE)
_GENERIC_PRODUCT_KIND = (
    r"(?:(?:мобильный\s+)?(?:телефон|смартфон)|"
    r"ноутбук|планшет|телевизор|монитор|видеокарта|процессор|"
    r"материнская\s+плата|наушники|гарнитура|"
    r"(?:умные|смарт[-\s]?)\s*часы|часы|"
    r"игровая\s+консоль|консоль|фотоаппарат|камера|принтер|"
    r"роутер|маршрутизатор|холодильник|стиральная\s+машина|"
    r"посудомоечная\s+машина|пылесос|духовой\s+шкаф|"
    r"варочная\s+панель|микроволновая\s+печь|кофемашина|"
    r"кондиционер|водонагреватель|фен|электробритва|"
    r"smartphone|mobile\s+phone|cell\s+phone|laptop|tablet|"
    r"television|tv|monitor|graphics\s+card|headphones|headset|"
    r"smartwatch|game\s+console|camera|printer|router|"
    r"refrigerator|washing\s+machine|vacuum\s+cleaner)"
)
_GENERIC_PRODUCT_PREFIX = re.compile(
    rf"^{_GENERIC_PRODUCT_KIND}\s*[:—-]?\s+",
    re.IGNORECASE,
)
_BRAND_WRAPPED_PRODUCT_KIND = re.compile(
    rf"^(?P<brand>[a-zа-я0-9][a-zа-я0-9.+-]*)\s+"
    rf"{_GENERIC_PRODUCT_KIND}\s+"
    rf"(?:(?P=brand)\s+)?",
    re.IGNORECASE,
)
_TRAILING_TECHNICAL_CODE = re.compile(
    r"(?:\s+|\s*[(\[])(?P<code>[A-ZА-Я0-9][A-ZА-Я0-9._/-]{4,}"
    r"(?:\s+(?:/\s*)?A)?)[)\]]?\s*$",
    re.IGNORECASE,
)


def selection_color_key(title: str | None) -> str | None:
    """Returns a stable UI key without collapsing exact marketing colors."""

    if not title:
        return None

    identity = extract_color_identity(title)
    if identity is not None and identity.confidence in {EXACT_VARIANT, UNKNOWN}:
        return identity.variant

    if _ISAI_BLUE_SUFFIX.search(title):
        return "isai_blue"

    return requested_color_key(title)


def selection_color_label(title: str) -> str | None:
    """Returns existing labels plus UI-only marketing color names."""

    if _ISAI_BLUE_SUFFIX.search(title) is not None:
        return "Isai Blue"
    identity = extract_color_identity(title)
    if identity is not None and identity.confidence == UNKNOWN:
        return extract_color_phrase(title)
    return legacy_color_label(title)


def group_selection_model_variants(
    products: Iterable[ProductCandidate],
) -> list[ProductVariantGroup]:
    """Groups by a color-neutral copy while returning original candidates."""

    product_list = list(products)
    originals = {product.key: product for product in product_list}
    normalized = [
        replace(
            product,
            title=selection_model_title(product.title),
        )
        for product in product_list
    ]
    normalized = _collapse_contextual_skus(normalized)
    normalized = [
        replace(product, title=selection_model_title(product.title))
        for product in normalized
    ]

    groups = group_model_variants(normalized)
    return [
        ProductVariantGroup(
            title=group.title,
            products=[originals[product.key] for product in group.products],
        )
        for group in groups
    ]


def selection_model_title(title: str) -> str:
    """Remove only confirmed color suffix and SIM labels from the UI stem."""
    result = without_sim(title)
    while True:
        previous = result
        result = _GENERIC_PRODUCT_PREFIX.sub("", result).strip()
        wrapped = _BRAND_WRAPPED_PRODUCT_KIND.search(result)
        if wrapped is not None:
            result = (
                wrapped.group("brand") + " " + result[wrapped.end():]
            ).strip()
        result = re.sub(
            r"^([a-zа-я0-9][a-zа-я0-9.+-]*)\s+\1\b",
            r"\1",
            result,
            flags=re.IGNORECASE,
        ).strip()
        if result == previous:
            break
    if re.search(r"\b(?:apple|iphone)\b", result, re.IGNORECASE):
        result = re.sub(r"\bapple\b", "Apple", result, flags=re.IGNORECASE)
        result = re.sub(r"\biphone\b", "iPhone", result, flags=re.IGNORECASE)
        result = " ".join(result.split()).strip(" -/,")
    if _ISAI_BLUE_SUFFIX.search(result):
        return _ISAI_BLUE_SUFFIX.sub("", result).strip(" -/,")
    phrase = extract_color_phrase(result)
    if phrase:
        for suffix in (f"({phrase})", phrase):
            if result.casefold().endswith(suffix.casefold()):
                return result[:-len(suffix)].strip(" -/,")
    return result


def _model_key(value: str) -> str:
    return re.sub(
        r"[^a-zа-я0-9]+",
        " ",
        value.casefold().replace("ё", "е"),
    ).strip()


def _trailing_technical_code(value: str) -> tuple[str, str] | None:
    match = _TRAILING_TECHNICAL_CODE.search(value)
    if match is None:
        return None
    code = re.sub(r"[^a-zа-я0-9]", "", match.group("code").casefold())
    if (
        len(code) < 6
        or re.search(r"[a-zа-я]", code) is None
        or re.search(r"\d", code) is None
    ):
        return None
    stem = value[:match.start()].strip(" -/,")
    # A lone brand plus a code means that the code is the actual model.
    if len(re.findall(r"[a-zа-я0-9]+", stem, re.IGNORECASE)) < 2:
        return None
    return stem, code


def _collapse_contextual_skus(
    products: list[ProductCandidate],
) -> list[ProductCandidate]:
    """Hide retailer SKUs only when sibling cards prove a common model."""

    parsed = {
        product.key: _trailing_technical_code(product.title)
        for product in products
    }
    bare_keys = {
        _model_key(selection_model_title(product.title))
        for product in products
        if parsed[product.key] is None
    }
    codes_by_stem: dict[str, set[str]] = {}
    colored_stems: set[str] = set()
    for item in parsed.values():
        if item is None:
            continue
        stem, code = item
        model_key = _model_key(selection_model_title(stem))
        codes_by_stem.setdefault(model_key, set()).add(code)
        if selection_color_key(stem) is not None:
            colored_stems.add(model_key)

    collapsible = {
        stem
        for stem, codes in codes_by_stem.items()
        if len(codes) >= 2 or stem in bare_keys or stem in colored_stems
    }
    return [
        replace(product, title=item[0])
        if (
            item is not None
            and _model_key(selection_model_title(item[0])) in collapsible
        )
        else product
        for product in products
        for item in (parsed[product.key],)
    ]
