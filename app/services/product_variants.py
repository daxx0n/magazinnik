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
_COLOR_ALIASES = {
    "black": ("black", "черн", "графит"),
    "white": ("white", "бел"),
    "blue": ("blue", "син", "голуб", "бирюз"),
    "green": ("green", "зелен"),
    "yellow": ("yellow", "желт"),
    "gold": ("gold", "золот"),
    "red": ("red", "красн"),
    "purple": ("purple", "фиолет", "сирен", "лилов"),
    "pink": ("pink", "розов"),
    "orange": ("orange", "оранж"),
    "gray": ("gray", "grey", "серый", "серая", "серое"),
    "silver": ("silver", "серебр"),
    "beige": ("beige", "беж", "коричн"),
}

_GENERIC_COLOR_LABELS = {
    "черный": "Black",
    "белый": "White",
    "синий": "Blue",
    "голубой": "Light Blue",
    "зеленый": "Green",
    "желтый": "Yellow",
    "золотистый": "Gold",
    "красный": "Red",
    "фиолетовый": "Purple",
    "сиреневый": "Lavender",
    "лиловый": "Lilac",
    "розовый": "Pink",
    "оранжевый": "Orange",
    "серый": "Gray",
    "серебристый": "Silver",
    "графитовый": "Graphite",
    "титановый": "Titanium",
    "бежевый": "Beige",
    "коричневый": "Brown",
    "бирюзовый": "Turquoise",
    "темно-синий": "Dark Blue",
    "темно-зеленый": "Dark Green",
}

_OFFICIAL_COLOR_LABELS = (
    (
        re.compile(r"\bapple\s+iphone\s+17\s+pro\b", re.I),
        {
            "оранжевый": "Cosmic Orange",
            "синий": "Deep Blue",
            "темно-синий": "Deep Blue",
            "серебристый": "Silver",
        },
    ),
    (
        re.compile(r"\bapple\s+iphone\s+17\b", re.I),
        {
            "черный": "Black",
            "белый": "White",
            "голубой": "Mist Blue",
            "синий": "Mist Blue",
            "зеленый": "Sage",
            "сиреневый": "Lavender",
            "фиолетовый": "Lavender",
        },
    ),
    (
        re.compile(r"\bapple\s+iphone\s+air\b", re.I),
        {
            "черный": "Space Black",
            "белый": "Cloud White",
            "голубой": "Sky Blue",
            "синий": "Sky Blue",
            "золотистый": "Light Gold",
        },
    ),
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

    if any(
        marker in normalized
        for marker in _COLOR_MARKERS
    ):
        return value

    # Фирменные названия вроде Obsidian или Porcelain
    # не всегда содержат обычное название цвета.
    latin_words = re.findall(r"[a-z]+", normalized)
    non_color_markers = {
        "dual",
        "edition",
        "esim",
        "max",
        "pro",
        "rev",
        "sim",
        "usb",
        "version",
        "with",
    }

    if (
        1 <= len(latin_words) <= 3
        and not re.search(r"\d", normalized)
        and not set(latin_words) & non_color_markers
    ):
        return value

    return None


def extract_color_key(title: str) -> str | None:
    """Нормализует русское или английское название цвета."""

    normalized = title.casefold()

    for color_key, aliases in _COLOR_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return color_key

    return None


def display_color(title: str) -> str | None:
    """Возвращает исходное или фирменное название цвета."""

    color = extract_color(title)

    if color is None:
        return None

    if re.search(r"[a-z]", color, re.IGNORECASE):
        return color

    normalized = (
        color.casefold()
        .replace("ё", "е")
        .replace("–", "-")
        .replace("—", "-")
    )
    normalized = " ".join(normalized.split())

    for title_pattern, labels in _OFFICIAL_COLOR_LABELS:
        if title_pattern.search(title):
            official_label = labels.get(normalized)

            if official_label is not None:
                return official_label

    return _GENERIC_COLOR_LABELS.get(
        normalized,
        color,
    )


def display_product_title(title: str) -> str:
    """Подставляет отображаемое название цвета в товар."""

    color = extract_color(title)
    display_label = display_color(title)

    if color is None or display_label is None:
        return title

    return re.sub(
        r"\([^()]*\)\s*$",
        f"({display_label})",
        title,
    )


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
