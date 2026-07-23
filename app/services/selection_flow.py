from __future__ import annotations

import re
from collections.abc import Iterable

from app.models.product import ProductCandidate
from app.services.product_variants import ProductVariantGroup, extract_memory, group_by_memory


def _natural_parts(value: str) -> tuple[tuple[int, int | str], ...]:
    """Создаёт ключ естественной сортировки для моделей вроде 17, 16 Pro, S25."""

    normalized = value.casefold().replace("ё", "е")
    parts: list[tuple[int, int | str]] = []
    for token in re.findall(r"\d+|[^\d]+", normalized):
        if token.isdigit():
            parts.append((1, int(token)))
        else:
            parts.append((0, " ".join(token.split())))
    return tuple(parts)


def ordered_variant_groups(
    products: Iterable[ProductCandidate],
    group_factory,
) -> list[ProductVariantGroup]:
    """Возвращает устройства от более новой/крупной модели к меньшей."""

    groups = list(group_factory(list(products)))
    return sorted(
        groups,
        key=lambda group: (_natural_parts(group.title), group.title.casefold()),
        reverse=True,
    )


def _memory_part_size(value: str) -> int:
    match = re.fullmatch(r"(\d+)(MB|GB|TB)", value.upper())
    if match is None:
        return 0
    amount = int(match.group(1))
    multiplier = {"MB": 1, "GB": 1024, "TB": 1024 * 1024}[match.group(2)]
    return amount * multiplier


def memory_sort_key(label: str) -> tuple[int, tuple[int, ...], str]:
    """Сортирует память от большей к меньшей; отсутствие памяти ставит в конец."""

    if label == "Без выбора":
        return (0, (), label)
    sizes = tuple(_memory_part_size(part) for part in label.split("/"))
    return (1, sizes, label.casefold())


def ordered_memory_groups(
    products: Iterable[ProductCandidate],
) -> list[tuple[str, list[ProductCandidate]]]:
    groups = group_by_memory(list(products))
    return sorted(groups, key=lambda item: memory_sort_key(item[0]), reverse=True)


def memory_label(product: ProductCandidate) -> str:
    return extract_memory(product.title) or "Без выбора"

def selectable_memory_groups(
    products: Iterable[ProductCandidate],
) -> list[tuple[str, list[ProductCandidate]]]:
    """Returns only explicit memory variants suitable for user selection."""

    return [
        group
        for group in ordered_memory_groups(products)
        if group[0] != "Без выбора"
    ]


def has_memory_choice(
    products: Iterable[ProductCandidate],
) -> bool:
    """True only when a model has at least two explicit memory variants."""

    return len(selectable_memory_groups(products)) > 1

