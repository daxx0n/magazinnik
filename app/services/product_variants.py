import re
from dataclasses import dataclass

from app.models.product import ProductCandidate


_MEMORY_PATTERN = re.compile(
    r"\b\d+\s*(?:gb|tb|mb|гб|тб|мб)\b",
    re.IGNORECASE,
)
_MEMORY_PAIR_PATTERN = re.compile(
    r"\b\d{1,2}\s*/\s*\d{3,4}\b"
)
_COLOR_MARKERS = (
    "black",
    "white",
    "blue",
    "green",
    "yellow",
    "red",
    "purple",
    "pink",
    "orange",
    "gray",
    "grey",
    "silver",
    "gold",
    "graphite",
    "titanium",
    "beige",
    "черн",
    "бел",
    "син",
    "голуб",
    "зелен",
    "желт",
    "красн",
    "фиолет",
    "сирен",
    "лилов",
    "розов",
    "оранж",
    "сер",
    "серебр",
    "золот",
    "графит",
    "титан",
    "беж",
    "коричн",
    "бирюз",
)


@dataclass(frozen=True, slots=True)
class ProductVariantGroup:
    """Одна модель со всеми её модификациями."""

    title: str
    products: list[ProductCandidate]


def extract_memory(title: str) -> str | None:
    """Извлекает память или конфигурацию RAM/storage."""

    memory_parts = _MEMORY_PATTERN.findall(title)

    if memory_parts:
        return "/".join(
            re.sub(r"\s+", "", part).upper()
            for part in memory_parts
        )

    pair = _MEMORY_PAIR_PATTERN.search(title)

    if pair:
        return re.sub(r"\s+", "", pair.group(0))

    return None


def extract_color(title: str) -> str | None:
    """Извлекает цвет из завершающей части в скобках."""

    match = re.search(r"\(([^()]*)\)\s*$", title)

    if match is None:
        return None

    value = match.group(1).strip()
    normalized = value.casefold()

    if not any(
        marker in normalized
        for marker in _COLOR_MARKERS
    ):
        return None

    return value


def base_product_title(title: str) -> str:
    """Убирает из названия память и цвет."""

    result = title
    color = extract_color(result)

    if color is not None:
        result = re.sub(
            r"\s*\([^()]*\)\s*$",
            "",
            result,
        )

    result = _MEMORY_PATTERN.sub(" ", result)
    result = _MEMORY_PAIR_PATTERN.sub(" ", result)
    result = re.sub(r"\s*/\s*", " ", result)

    return " ".join(result.split()).strip(" -/,")


def group_product_variants(
    products: list[ProductCandidate],
) -> list[ProductVariantGroup]:
    """Объединяет память и цвета одной модели."""

    groups: dict[str, list[ProductCandidate]] = {}
    titles: dict[str, str] = {}

    for product in products:
        base_title = base_product_title(product.title)
        key = base_title.casefold()
        groups.setdefault(key, []).append(product)
        titles.setdefault(key, base_title)

    return [
        ProductVariantGroup(
            title=titles[key],
            products=group_products,
        )
        for key, group_products in groups.items()
    ]


def group_by_memory(
    products: list[ProductCandidate],
) -> list[tuple[str, list[ProductCandidate]]]:
    """Группирует карточки по конфигурации памяти."""

    groups: dict[str, list[ProductCandidate]] = {}

    for product in products:
        label = extract_memory(product.title) or "Без выбора"
        groups.setdefault(label, []).append(product)

    return list(groups.items())
