import re
from dataclasses import dataclass

from app.models.product import ProductCandidate


_MEMORY_PATTERN = re.compile(
    r"\b(\d+)\s*(gb|tb|mb|гб|тб|мб)\b",
    re.IGNORECASE,
)
_MEMORY_PAIR_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})\s*"
    r"(gb|tb|mb|гб|тб|мб)?\s*/\s*"
    r"(\d{1,4})\s*"
    r"(gb|tb|mb|гб|тб|мб)?(?!\w)",
    re.IGNORECASE,
)
_COLOR_PATTERNS = (
    (
        "natural_titanium",
        re.compile(
            r"\b(?:natural\s+titanium|природн\w*\s+титан\w*)\b",
            re.I,
        ),
    ),
    (
        "desert_titanium",
        re.compile(
            r"\b(?:desert\s+titanium|пустынн\w*\s+титан\w*)\b",
            re.I,
        ),
    ),
    (
        "black_titanium",
        re.compile(
            r"\b(?:black\s+titanium|черн\w*\s+титан\w*)\b",
            re.I,
        ),
    ),
    (
        "white_titanium",
        re.compile(
            r"\b(?:white\s+titanium|бел\w*\s+титан\w*)\b",
            re.I,
        ),
    ),
    (
        "blue_titanium",
        re.compile(
            r"\b(?:blue\s+titanium|син\w*\s+титан\w*)\b",
            re.I,
        ),
    ),
    (
        "graphite",
        re.compile(r"\b(?:graphite|графитов\w*)\b", re.I),
    ),
    (
        "light_blue",
        re.compile(
            r"\b(?:light\s+blue|mist\s+blue|sky\s+blue|"
            r"голуб\w*)\b",
            re.I,
        ),
    ),
    (
        "dark_blue",
        re.compile(
            r"\b(?:dark\s+blue|deep\s+blue|navy|темно[-\s]+син\w*)\b",
            re.I,
        ),
    ),
    (
        "turquoise",
        re.compile(r"\b(?:turquoise|teal|бирюз\w*)\b", re.I),
    ),
    (
        "lavender",
        re.compile(r"\b(?:lavender|сирен\w*)\b", re.I),
    ),
    (
        "lilac",
        re.compile(r"\b(?:lilac|лилов\w*)\b", re.I),
    ),
    (
        "black",
        re.compile(
            r"\b(?:black|obsidian|space\s+black|черн\w*)\b",
            re.I,
        ),
    ),
    (
        "white",
        re.compile(
            r"\b(?:white|porcelain|cloud\s+white|бел\w*)\b",
            re.I,
        ),
    ),
    (
        "blue",
        re.compile(
            r"\b(?:blue|син\w*)\b",
            re.I,
        ),
    ),
    (
        "midnight",
        re.compile(r"\b(?:midnight|полуночн\w*)\b", re.I),
    ),
    (
        "starlight",
        re.compile(
            r"\b(?:starlight|сияющ\w*\s+звезд\w*)\b",
            re.I,
        ),
    ),
    (
        "dark_green",
        re.compile(
            r"\b(?:dark\s+green|темно[-\s]+зелен\w*)\b",
            re.I,
        ),
    ),
    (
        "green",
        re.compile(r"\b(?:green|sage|зелен\w*)\b", re.I),
    ),
    (
        "yellow",
        re.compile(r"\b(?:yellow|желт\w*)\b", re.I),
    ),
    (
        "rose_gold",
        re.compile(
            r"\b(?:rose\s+gold|розов\w*\s+золот\w*)\b",
            re.I,
        ),
    ),
    (
        "light_gold",
        re.compile(
            r"\b(?:light\s+gold|светло[-\s]+золот\w*)\b",
            re.I,
        ),
    ),
    (
        "gold",
        re.compile(r"\b(?:gold|золот\w*)\b", re.I),
    ),
    (
        "red",
        re.compile(r"\b(?:red|красн\w*)\b", re.I),
    ),
    (
        "purple",
        re.compile(r"\b(?:purple|фиолет\w*)\b", re.I),
    ),
    (
        "pink",
        re.compile(r"\b(?:pink|розов\w*)\b", re.I),
    ),
    (
        "orange",
        re.compile(
            r"\b(?:orange|cosmic\s+orange|оранж\w*)\b",
            re.I,
        ),
    ),
    (
        "gray",
        re.compile(r"\b(?:gray|grey|сер(?:ый|ая|ое|ые))\b", re.I),
    ),
    (
        "silver",
        re.compile(r"\b(?:silver|серебр\w*)\b", re.I),
    ),
    (
        "beige",
        re.compile(r"\b(?:beige|беж\w*)\b", re.I),
    ),
    (
        "brown",
        re.compile(r"\b(?:brown|коричн\w*)\b", re.I),
    ),
    (
        "burgundy",
        re.compile(r"\b(?:burgundy|бордов\w*)\b", re.I),
    ),
    (
        "cream",
        re.compile(r"\b(?:cream|кремов\w*)\b", re.I),
    ),
    (
        "bronze",
        re.compile(r"\b(?:bronze|бронзов\w*)\b", re.I),
    ),
    (
        "copper",
        re.compile(r"\b(?:copper|медн\w*)\b", re.I),
    ),
    (
        "mint",
        re.compile(r"\b(?:mint|мятн\w*)\b", re.I),
    ),
    (
        "nickel",
        re.compile(r"\b(?:nickel|никел\w*)\b", re.I),
    ),
    (
        "titanium",
        re.compile(r"\b(?:titanium|титан\w*)\b", re.I),
    ),
)

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
    "природный титан": "Natural Titanium",
    "пустынный титан": "Desert Titanium",
    "черный титан": "Black Titanium",
    "белый титан": "White Titanium",
    "синий титан": "Blue Titanium",
    "полуночный": "Midnight",
    "сияющая звезда": "Starlight",
    "бордовый": "Burgundy",
    "кремовый": "Cream",
    "бронзовый": "Bronze",
    "медный": "Copper",
    "мятный": "Mint",
    "никель": "Nickel",
    "матовый черный": "Matte Black",
    "космический оранжевый": "Cosmic Orange",
    "розовое золото": "Rose Gold",
    "светло-золотистый": "Light Gold",
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

    pair = _find_memory_pair(title)

    if pair is not None:
        _, memory_parts = pair
        return "/".join(memory_parts)

    memory_parts = [
        _normalize_memory_part(amount, unit)
        for amount, unit in _MEMORY_PATTERN.findall(title)
    ]

    if memory_parts:
        return "/".join(
            sorted(
                memory_parts,
                key=_memory_part_size,
            )
        )

    return None


def _find_memory_pair(
    title: str,
) -> tuple[re.Match[str], list[str]] | None:
    """Находит RAM/storage, включая запись 8/256GB."""

    for match in _MEMORY_PAIR_PATTERN.finditer(title):
        left_amount, left_unit, right_amount, right_unit = (
            match.groups()
        )

        if (
            left_unit is None
            and right_unit is None
            and int(right_amount) < 32
        ):
            continue

        parts = [
            _normalize_memory_part(
                left_amount,
                left_unit or "GB",
            ),
            _normalize_memory_part(
                right_amount,
                right_unit or "GB",
            ),
        ]

        return match, sorted(parts, key=_memory_part_size)

    return None


def _normalize_memory_part(amount: str, unit: str) -> str:
    unit_aliases = {
        "гб": "GB",
        "тб": "TB",
        "мб": "MB",
    }
    normalized_unit = unit_aliases.get(
        unit.casefold(),
        unit.upper(),
    )
    return f"{int(amount)}{normalized_unit}"


def _memory_part_size(value: str) -> int:
    match = re.fullmatch(r"(\d+)(MB|GB|TB)", value)

    if match is None:
        return 0

    amount = int(match.group(1))
    multiplier = {
        "MB": 1,
        "GB": 1024,
        "TB": 1024 * 1024,
    }[match.group(2)]
    return amount * multiplier


def extract_color(title: str) -> str | None:
    """Извлекает цвет из завершающей части в скобках."""

    match = re.search(r"\(([^()]*)\)\s*$", title)

    if match is None:
        return None

    value = match.group(1).strip()
    normalized = " ".join(value.casefold().split())

    if _match_color_key(normalized) is not None:
        return value

    return None


def extract_color_key(title: str) -> str | None:
    """Нормализует русское или английское название цвета."""

    explicit_color = extract_color(title)

    if explicit_color is not None:
        color_key = _match_color_key(
            display_color(title) or explicit_color
        )

        if color_key is not None:
            return color_key

        return "name:" + re.sub(
            r"[^a-z0-9]+",
            "_",
            explicit_color.casefold(),
        ).strip("_")

    return _match_color_key(title)


def _match_color_key(value: str) -> str | None:
    """Ищет цвет только как отдельное слово или фразу."""

    for color_key, pattern in _COLOR_PATTERNS:
        if pattern.search(value):
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

    direct_label = _GENERIC_COLOR_LABELS.get(normalized)

    if direct_label is not None:
        return direct_label

    parts = [part.strip() for part in color.split("/")]

    if len(parts) > 1:
        translated_parts = [
            _GENERIC_COLOR_LABELS.get(
                " ".join(part.casefold().split()),
                part,
            )
            for part in parts
        ]
        return "/".join(translated_parts)

    return color


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

    pair = _find_memory_pair(result)

    if pair is not None:
        pair_match, _ = pair
        result = (
            result[:pair_match.start()]
            + " "
            + result[pair_match.end():]
        )

    result = _MEMORY_PATTERN.sub(" ", result)
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

    def memory_group_sort_key(
        item: tuple[str, list[ProductCandidate]],
    ) -> tuple[int, int, str]:
        label = item[0]

        if label == "Без выбора":
            return (1, 0, label)

        sizes = [
            _memory_part_size(part)
            for part in label.split("/")
        ]

        return (
            0,
            max(sizes, default=0),
            "/".join(
                f"{size:012d}"
                for size in sizes
            ),
        )

    return sorted(
        groups.items(),
        key=memory_group_sort_key,
    )
