"""Shared color normalization for cross-source product matching.

The module distinguishes exact manufacturer variants from generic base colors.
Exact variants only match confirmed aliases of the same variant; a generic base
color may match any recognized variant in the same family.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


EXACT_VARIANT = "exact_variant"
BASE_COLOR = "base_color"
UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ColorIdentity:
    family: str
    variant: str
    confidence: str

    @property
    def key(self) -> str:
        if self.confidence in {EXACT_VARIANT, UNKNOWN}:
            return self.variant
        return self.family


_VARIANT_ALIASES: dict[str, tuple[str, set[str]]] = {
    "mint": (
        "green",
        {
            "mint",
            "mint green",
            "green mint",
            "мятный",
            "мятный зеленый",
            "зеленый мятный",
            "мятно зеленый",
        },
    ),
    "hazel": (
        "brown",
        {"hazel", "лесной орех", "ореховый"},
    ),
    "jade": (
        "green",
        {
            "jade",
            "jade green",
            "green jade",
            "нефрит",
            "нефритовый",
            "нефритовый зеленый",
        },
    ),
    "obsidian": ("black", {"obsidian", "обсидиан"}),
    "porcelain": ("white", {"porcelain", "фарфор", "фарфоровый"}),
    "moonstone": ("gray", {"moonstone", "лунный камень"}),
    "snow": ("white", {"snow", "снег", "снежный"}),
    "mist": ("gray", {"mist", "fog", "туман", "туманный"}),
    "lemongrass": ("green", {"lemongrass", "лемонграсс"}),
    "berry": ("pink", {"berry", "ягода", "ягодный"}),
    "peony": ("pink", {"peony", "пион", "пионовый"}),
    "bay": ("blue", {"bay", "залив"}),
    "indigo": ("blue", {"indigo", "индиго"}),
    "natural_titanium": (
        "gray",
        {
            "natural titanium",
            "натуральный титан",
            "природный титан",
            "титановый натуральный",
        },
    ),
    "blue_titanium": (
        "blue",
        {"blue titanium", "titanium blue", "синий титан", "титановый синий"},
    ),
    "black_titanium": (
        "black",
        {
            "black titanium",
            "titanium black",
            "черный титан",
            "титановый черный",
        },
    ),
    "white_titanium": (
        "white",
        {
            "white titanium",
            "titanium white",
            "белый титан",
            "титановый белый",
        },
    ),
    "titanium_gray": (
        "gray",
        {
            "titanium gray",
            "titanium grey",
            "gray titanium",
            "grey titanium",
            "титановый серый",
            "серый титан",
        },
    ),
    "titanium_violet": (
        "purple",
        {
            "titanium violet",
            "violet titanium",
            "титановый фиолетовый",
            "фиолетовый титан",
        },
    ),
    "midnight": ("black", {"midnight", "полуночный"}),
    "midnight_black": (
        "black",
        {"midnight black", "полуночный черный"},
    ),
    "space_black": ("black", {"space black", "космический черный"}),
    "phantom_black": ("black", {"phantom black", "фантомный черный"}),
    "charcoal": ("black", {"charcoal", "угольный"}),
    "graphite": ("gray", {"graphite", "графит", "графитовый"}),
    "forest_green": (
        "green",
        {"forest green", "лесной зеленый", "зеленый лесной"},
    ),
    "ocean_blue": (
        "blue",
        {"ocean blue", "океанский синий", "синий океан"},
    ),
    "navy": ("blue", {"navy", "темно синий", "темно синий цвет"}),
    "deep_blue": ("blue", {"deep blue", "глубокий синий"}),
    "mist_blue": ("blue", {"mist blue", "туманный синий"}),
    "sky_blue": ("blue", {"sky blue", "небесно голубой"}),
    "sage": ("green", {"sage", "шалфей"}),
    "seafoam": ("green", {"seafoam", "морская пена"}),
    "lavender": ("purple", {"lavender", "лаванда", "лавандовый"}),
    "lilac": ("purple", {"lilac", "сиреневый", "лиловый"}),
    "storm_grey": ("gray", {"storm grey", "storm gray", "штормовой серый"}),
    "glacier_white": ("white", {"glacier white", "ледниковый белый"}),
    "cloud_white": ("white", {"cloud white", "облачный белый"}),
    "frost": ("white", {"frost", "фрост", "морозный белый"}),
    "rose_gold": ("gold", {"rose gold", "розовое золото"}),
    "cosmic_orange": ("orange", {"cosmic orange", "космический оранжевый"}),
}

_BASE_COLOR_ALIASES: dict[str, set[str]] = {
    "black": {"black", "черный"},
    "white": {"white", "белый"},
    "green": {"green", "зеленый"},
    "blue": {"blue", "синий", "голубой"},
    "gray": {"gray", "grey", "серый"},
    "brown": {"brown", "коричневый"},
    "purple": {"purple", "violet", "фиолетовый"},
    "pink": {"pink", "розовый"},
    "red": {"red", "красный"},
    "yellow": {"yellow", "желтый"},
    "orange": {"orange", "оранжевый"},
    "gold": {"gold", "золотой", "золотистый"},
    "silver": {"silver", "серебристый", "серебряный"},
    "beige": {"beige", "бежевый"},
    "turquoise": {"turquoise", "teal", "бирюзовый"},
    "bronze": {"bronze", "бронзовый"},
    "copper": {"copper", "медный"},
}

_NON_WORD_RE = re.compile(r"[^0-9a-zа-я]+", re.IGNORECASE)
_TECHNICAL_PARENTHETICAL = re.compile(
    r"^(?:wi[- ]?fi|lte|5g|4g|global|china|cn|eu|us|usa|"
    r"dual\s*sim|single\s*sim|esim|refurbished|renewed|"
    r"digital\s+edition|gps(?:\s*\+\s*cellular)?|cellular|"
    r"уценк\w*|восстановлен\w*|без\s+дисковод\w*|"
    r"с\s+дисковод\w*|с\s+разъем\w*.*|без\s+разъем\w*.*)$",
    re.IGNORECASE,
)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.casefold().replace("ё", "е")
    normalized = _NON_WORD_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def _alias_index() -> dict[str, ColorIdentity]:
    aliases: dict[str, ColorIdentity] = {}
    for variant, (family, values) in _VARIANT_ALIASES.items():
        identity = ColorIdentity(
            family=family,
            variant=variant,
            confidence=EXACT_VARIANT,
        )
        for value in values:
            aliases[_normalize_text(value)] = identity

    for family, values in _BASE_COLOR_ALIASES.items():
        identity = ColorIdentity(
            family=family,
            variant=family,
            confidence=BASE_COLOR,
        )
        for value in values:
            aliases.setdefault(_normalize_text(value), identity)
    return aliases


_ALIASES = _alias_index()
_MAX_ALIAS_WORDS = max(len(alias.split()) for alias in _ALIASES)


def _identity_for_phrase(value: str) -> ColorIdentity | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    return _ALIASES.get(normalized)


def normalize_color(value: str | None) -> ColorIdentity | None:
    """Finds the strongest recognized color identity in arbitrary text."""

    if not value:
        return None

    text = _normalize_text(value)
    if not text:
        return None

    padded = f" {text} "
    matches: list[tuple[int, int, int, ColorIdentity]] = []
    for alias, identity in _ALIASES.items():
        marker = f" {alias} "
        position = padded.rfind(marker)
        if position < 0:
            continue
        matches.append(
            (
                position + len(marker),
                int(identity.confidence == EXACT_VARIANT),
                len(alias.split()),
                identity,
            )
        )

    if not matches:
        return None
    return max(matches, key=lambda item: item[:3])[3]


def extract_color_phrase(value: str | None) -> str | None:
    """Returns an explicit trailing color phrase without touching model words."""

    if not value:
        return None

    text = " ".join(value.split()).strip()
    trailing = re.search(r"\(([^()]*)\)\s*$", text)
    if trailing is not None:
        phrase = trailing.group(1).strip()
        if _identity_for_phrase(phrase) is not None:
            return phrase
        normalized_phrase = _normalize_text(phrase)
        if (
            normalized_phrase
            and len(phrase) <= 40
            and not any(character.isdigit() for character in phrase)
            and re.search(r"[,;+]", phrase) is None
            and _TECHNICAL_PARENTHETICAL.fullmatch(phrase) is None
        ):
            return phrase
        return None

    tokens = text.split()
    for width in range(min(_MAX_ALIAS_WORDS, len(tokens)), 0, -1):
        phrase = " ".join(tokens[-width:]).strip("()[]{}.,;:-_/ ")
        if phrase and _identity_for_phrase(phrase) is not None:
            return phrase
    return None


def extract_color_identity(value: str | None) -> ColorIdentity | None:
    phrase = extract_color_phrase(value)
    if phrase is None:
        return None
    identity = _identity_for_phrase(phrase)
    if identity is not None:
        return identity
    normalized = _normalize_text(phrase)
    return ColorIdentity(
        family="unknown",
        variant=f"name:{normalized.replace(' ', '_')}",
        confidence=UNKNOWN,
    )


def color_identities_match(
    requested: ColorIdentity,
    candidate: ColorIdentity,
) -> bool:
    if requested.confidence == UNKNOWN:
        return (
            candidate.confidence == UNKNOWN
            and requested.variant == candidate.variant
        )
    if requested.confidence == EXACT_VARIANT:
        return (
            candidate.confidence == EXACT_VARIANT
            and requested.variant == candidate.variant
        )
    return (
        candidate.confidence != UNKNOWN
        and requested.family == candidate.family
    )


def colors_match(requested: str | None, candidate: str | None) -> bool:
    """Matches aliases safely, failing closed for an explicit unknown color."""

    if not requested:
        return True

    requested_identity = normalize_color(requested)
    candidate_identity = normalize_color(candidate)
    if requested_identity is None or candidate_identity is None:
        return False
    return color_identities_match(requested_identity, candidate_identity)
