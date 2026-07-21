from pathlib import Path

path = Path("app/services/model_selection.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    'r"cloud\\s+white|white|бел\\w*)\\b",',
    'r"cloud\\s+white|frost|фрост\\w*|white|бел\\w*)\\b",',
)
text = text.replace(
    'r"\\b(?:hazel|lemongrass|mint|sage|green|"\n            r"мятн\\w*|зелен\\w*)\\b",',
    'r"\\b(?:hazel|lemongrass|forest\\s+hazel|jade|mint|sage|green|"\n            r"нефрит\\w*|лемонграсс\\w*|лесн\\w*\\s+орех\\w*|"\n            r"мятн\\w*|зелен\\w*)\\b",',
)
text = text.replace(
    'r"\\b(?:bay|blue|navy|голуб\\w*|син\\w*)\\b",',
    'r"\\b(?:bay|blue|navy|indigo|индиго\\w*|голуб\\w*|син\\w*)\\b",',
)
text = text.replace(
    'r"\\b(?:peony|rose|pink|розов\\w*)\\b",',
    'r"\\b(?:peony|rose|berry|pink|ягод\\w*|розов\\w*)\\b",',
)
text = text.replace(
    'r"\\b(?:graphite|gray|grey|сер(?:ый|ая|ое|ые)|"\n            r"графитов\\w*)\\b",',
    'r"\\b(?:graphite|moonstone|mist|fog|gray|grey|"\n            r"лунн\\w*\\s+камень|туман\\w*|сер(?:ый|ая|ое|ые)|"\n            r"графитов\\w*)\\b",',
)
text = text.replace(
    'r"\\b(?:lavender|lilac|purple|сирен\\w*|"',
    'r"\\b(?:lavender|lilac|purple|лаванд\\w*|сирен\\w*|"',
)

old = '''def group_model_variants(
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
'''
new = '''def group_model_variants(
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
        if contextual is not None and _model_key(contextual) in contextual_stems:
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
    r"dual\\s*sim|single\\s*sim|esim|refurbished|renewed|"
    r"уценк\\w*|восстановлен\\w*|без\\s+дисковода)$",
    re.IGNORECASE,
)


def _parenthetical_stem(title: str) -> str | None:
    match = re.search(r"\\s*\\(([^()]*)\\)\\s*$", title)
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
        suffix_match = re.search(r"\\(([^()]*)\\)\\s*$", product.title)
        if suffix_match is None:
            continue
        key = _model_key(model_variant_title(stem))
        variants.setdefault(key, set()).add(suffix_match.group(1).casefold())
    return {
        key
        for key, suffixes in variants.items()
        if len(suffixes) >= 2 or key in bare_keys
    }
'''
if old not in text:
    raise RuntimeError("group_model_variants block not found")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
