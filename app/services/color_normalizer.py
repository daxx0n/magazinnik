"""Color normalization helpers for cross-source product matching.

Keeps exact manufacturer variants separate while allowing multilingual aliases.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorIdentity:
    family: str
    variant: str


_ALIASES = {
    "black": {
        "black", "черный", "чёрный", "obsidian", "обсидиан",
        "midnight", "space black", "graphite",
    },
    "white": {
        "white", "белый", "porcelain", "фарфор", "frost", "фрост",
    },
    "green": {
        "green", "зеленый", "зелёный", "mint", "mint green",
        "мятный", "мятный зеленый", "jade", "нефрит", "sage",
        "seafoam",
    },
    "blue": {
        "blue", "синий", "голубой", "navy", "bay", "indigo", "индиго",
    },
    "gray": {
        "gray", "grey", "серый", "graphite", "graphite gray",
        "moonstone", "лунный камень", "mist", "туман",
    },
    "purple": {
        "purple", "фиолетовый", "лаванда", "lavender", "lilac",
    },
    "pink": {
        "pink", "розовый", "berry", "ягода", "rose",
    },
    "brown": {
        "brown", "коричневый", "hazel", "лесной орех", "walnut",
    },
}


_VARIANT_ALIASES = {
    "mint": {"mint", "mint green", "мятный", "мятный зеленый"},
    "hazel": {"hazel", "лесной орех", "walnut"},
    "obsidian": {"obsidian", "обсидиан", "space black"},
    "moonstone": {"moonstone", "лунный камень"},
    "jade": {"jade", "нефрит"},
}


def normalize_color(value: str | None) -> ColorIdentity | None:
    if not value:
        return None

    text = " ".join(value.casefold().replace("ё", "е").split())
    for variant, aliases in _VARIANT_ALIASES.items():
        for alias in aliases:
            if alias in text:
                family = next(
                    family for family, family_aliases in _ALIASES.items()
                    if alias in family_aliases
                )
                return ColorIdentity(family=family, variant=variant)

    for family, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in text:
                return ColorIdentity(family=family, variant=alias)
    return None


def colors_match(requested: str | None, candidate: str | None) -> bool:
    req = normalize_color(requested)
    cand = normalize_color(candidate)

    if req is None:
        return True
    if cand is None:
        return False

    return req.variant == cand.variant
