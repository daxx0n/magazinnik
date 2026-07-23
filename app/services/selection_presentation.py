"""Presentation-only normalization for model and color selection screens.

These helpers intentionally do not change the production offer matcher. They
only control how search results are grouped and deduplicated in Telegram UI.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace

from app.models.product import ProductCandidate
from app.services.color_normalizer import EXACT_VARIANT, extract_color_identity
from app.services.model_selection import (
    group_model_variants,
    requested_color_key,
    selected_color_label as legacy_color_label,
)
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
    """Returns existing labels plus UI-only marketing color names."""

    if _ISAI_BLUE_SUFFIX.search(title) is not None:
        return "Isai Blue"
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
            title=_ISAI_BLUE_SUFFIX.sub("", product.title).strip(" -/,")
            if _ISAI_BLUE_SUFFIX.search(product.title)
            else product.title,
        )
        for product in product_list
    ]

    groups = group_model_variants(normalized)
    return [
        ProductVariantGroup(
            title=group.title,
            products=[originals[product.key] for product in group.products],
        )
        for group in groups
    ]
