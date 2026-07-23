"""Presentation-only normalization for model and color selection screens.

These helpers intentionally do not change the production offer matcher. They
only control how search results are grouped and deduplicated in Telegram UI.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.models.product import ProductCandidate
from app.services.color_normalizer import EXACT_VARIANT, extract_color_identity
from app.services.model_selection import group_model_variants, requested_color_key
from app.services.product_variants import ProductVariantGroup


_ISAI_BLUE_SUFFIX = re.compile(r"\s+isai[-\s]+blue\s*$", re.IGNORECASE)


def selection_color_key(title: str | None) -> str | None:
    """Returns a stable UI key without collapsing exact marketing colors."""

    if not title:
        return None

    identity = extract_color_identity(title)
    if identity is not None and identity.confidence == EXACT_VARIANT:
        return identity.variant

    if _ISAI_BLUE_SUFFIX.search(title):
        return "isai_blue"

    return requested_color_key(title)


def selection_color_label(title: str) -> str | None:
    """Returns a label for UI-only colors not known by the legacy formatter."""

    match = _ISAI_BLUE_SUFFIX.search(title)
    if match is not None:
        return "Isai Blue"
    return None


def group_selection_model_variants(
    products: Iterable[ProductCandidate],
) -> list[ProductVariantGroup]:
    """Keeps existing grouping but removes UI-only trailing color names."""

    groups = group_model_variants(products)
    merged: dict[str, list[ProductCandidate]] = {}
    titles: dict[str, str] = {}

    for group in groups:
        title = _ISAI_BLUE_SUFFIX.sub("", group.title).strip(" -/,")
        key = re.sub(
            r"[^a-zа-я0-9]+",
            " ",
            title.casefold().replace("ё", "е"),
        ).strip()
        merged.setdefault(key, []).extend(group.products)
        titles.setdefault(key, title)

    return [
        ProductVariantGroup(title=titles[key], products=group_products)
        for key, group_products in merged.items()
    ]
