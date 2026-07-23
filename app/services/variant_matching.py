"""Normalize material product variants before cross-source matching."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BundleIdentity:
    marker: str | None
    count: int | None = None


_MEMORY_PAIR_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*(gb|tb|mb|гб|тб|мб)?\s*/\s*"
    r"(\d{1,4})\s*(gb|tb|mb|гб|тб|мб)?(?!\w)",
    re.IGNORECASE,
)
_MEMORY_RE = re.compile(r"\b(\d+)\s*(gb|tb|mb|гб|тб|мб)\b", re.IGNORECASE)

_REGION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("global", re.compile(r"\b(?:global|international|международн\w*)\b", re.I)),
    ("eu", re.compile(r"\b(?:eu|eac|europe|европ\w*)\b", re.I)),
    ("us", re.compile(r"\b(?:us|usa|united\s+states|американск\w*)\b", re.I)),
    ("cn", re.compile(r"\b(?:cn|china|китайск\w*|китай)\b", re.I)),
    ("hk", re.compile(r"\b(?:hk|hong\s+kong|гонконг\w*)\b", re.I)),
    ("jp", re.compile(r"\b(?:jp|japan|японск\w*|япония)\b", re.I)),
    ("kr", re.compile(r"\b(?:kr|korea|корейск\w*|корея)\b", re.I)),
    ("in", re.compile(r"\b(?:india|индийск\w*|индия)\b", re.I)),
)

_BUNDLE_ITEMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "controller",
        re.compile(
            r"\b(?:controllers?|dualsense|gamepads?|контроллер\w*|геймпад\w*)\b",
            re.I,
        ),
    ),
    (
        "headset",
        re.compile(r"\b(?:headsets?|headphones?|наушник\w*|гарнитур\w*)\b", re.I),
    ),
    ("game", re.compile(r"\b(?:games?|игр\w*)\b", re.I)),
    (
        "charger",
        re.compile(r"\b(?:chargers?|adapter|зарядн\w*|адаптер\w*)\b", re.I),
    ),
    ("keyboard", re.compile(r"\b(?:keyboards?|клавиатур\w*)\b", re.I)),
    ("mouse", re.compile(r"\b(?:mice|mouse|мыш\w*)\b", re.I)),
    (
        "stylus",
        re.compile(r"\b(?:stylus|pen|карандаш\w*|стилус\w*)\b", re.I),
    ),
    ("case", re.compile(r"\b(?:cases?|covers?|чехл\w*|чехол\w*)\b", re.I)),
    ("dock", re.compile(r"\b(?:docks?|станци\w*)\b", re.I)),
)

_CONDITION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "refurbished",
        re.compile(
            r"\b(?:refurbished|renewed|reconditioned|certified\s+refurbished|"
            r"восстановлен\w*|как\s+нов\w*)\b",
            re.I,
        ),
    ),
    (
        "used",
        re.compile(
            r"(?:\bused\b|\bpre[-\s]?owned\b|\bб\s*/\s*у\b|"
            r"бывш\w*\s+в\s+употреблен\w*)",
            re.I,
        ),
    ),
    (
        "open_box",
        re.compile(
            r"\b(?:open[-\s]?box|витринн\w*|уценен\w*|уценк\w*|"
            r"поврежден\w*\s+упаковк\w*)\b",
            re.I,
        ),
    ),
)

_DISPLAY_CONFIGURATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "without_display",
        re.compile(
            r"\b(?:без\s+(?:час\w*|диспле\w*|экран\w*)|"
            r"without\s+(?:clock|display|screen))\b",
            re.I,
        ),
    ),
    (
        "with_display",
        re.compile(
            r"\b(?:(?:с|со)\s+(?:час\w*|диспле\w*|экран\w*)|"
            r"with\s+(?:clock|display|screen))\b",
            re.I,
        ),
    ),
)


_VARIANT_REMOVERS = (
    re.compile(
        r"\b(?:dual\s+e[-\s]?sim|dual\s+sim|single\s+sim|"
        r"(?:nano[-\s]?)?sim\s*\+\s*e[-\s]?sim|"
        r"(?:только\s+)?e[-\s]?sim|2\s*(?:x\s*)?(?:nano[-\s]?)?sim)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:wi[-\s]?fi|4g|5g|lte|gps\s*\+\s*cellular|gps|cellular)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:digital\s+edition|без\s+дисковод\w*|с\s+дисковод\w*)\b",
        re.I,
    ),
    re.compile(r"\b(?:usb\s*(?:type[-\s]*)?c|lightning)\b", re.I),
    re.compile(
        r"\b(?:русск\w*|russian|английск\w*|english)\s+озвучк\w*\b",
        re.I,
    ),
)


def _normalize(value: str) -> str:
    return value.casefold().replace("ё", "е")


def _memory_size(amount: str, unit: str) -> int:
    multiplier = {
        "mb": 1,
        "мб": 1,
        "gb": 1024,
        "гб": 1024,
        "tb": 1024 * 1024,
        "тб": 1024 * 1024,
    }[unit.casefold()]
    return int(amount) * multiplier


def memory_signature(value: str | None) -> frozenset[int]:
    if not value:
        return frozenset()

    pair = _MEMORY_PAIR_RE.search(value)
    if pair is not None:
        left_amount, left_unit, right_amount, right_unit = pair.groups()
        if left_unit is None and right_unit is None and int(right_amount) < 32:
            return frozenset()
        return frozenset(
            {
                _memory_size(left_amount, left_unit or "gb"),
                _memory_size(right_amount, right_unit or "gb"),
            }
        )

    return frozenset(
        _memory_size(amount, unit)
        for amount, unit in _MEMORY_RE.findall(value)
    )


def explicit_region(value: str | None) -> str | None:
    if not value:
        return None
    for region, pattern in _REGION_PATTERNS:
        if pattern.search(value):
            return region
    return None


def sim_configuration(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize(value)

    if re.search(r"\bdual\s+e[-\s]?sim\b", normalized):
        return "dual_esim"
    if re.search(
        r"\b(?:nano[-\s]?)?sim\s*\+\s*e[-\s]?sim\b",
        normalized,
    ):
        return "hybrid"
    if re.search(r"\b(?:только\s+)?e[-\s]?sim\b", normalized):
        return "esim_only"
    if re.search(
        r"\b(?:dual\s+sim|2\s*(?:x\s*)?(?:nano[-\s]?)?sim)\b",
        normalized,
    ):
        return "dual_sim"
    if re.search(r"\bsingle\s+sim\b", normalized):
        return "single_sim"
    return None


def device_configuration(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize(value)

    if re.search(r"\b(?:digital\s+edition|без\s+дисковод\w*)\b", normalized):
        return "digital"
    if re.search(r"\bс\s+дисковод\w*\b", normalized):
        return "disc"
    if re.search(r"\bgps\s*\+\s*cellular\b", normalized):
        return "gps_cellular"
    if re.search(r"\b5g\b", normalized):
        return "5g"
    if re.search(r"\b(?:4g|lte)\b", normalized):
        return "4g"
    if re.search(r"\bgps\b", normalized):
        return "gps"
    if re.search(r"\bwi[-\s]?fi\b", normalized):
        return "wifi"
    if re.search(r"\bcellular\b", normalized):
        return "cellular"
    return None


def connector_configuration(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize(value)
    if re.search(r"\blightning\b", normalized):
        return "lightning"
    if re.search(r"\busb\s*(?:type[-\s]*)?c\b", normalized):
        return "usb_c"
    return None


def voice_configuration(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize(value)
    if re.search(r"\b(?:русск\w*|russian)\s+озвучк\w*\b", normalized):
        return "voice_ru"
    if re.search(r"\b(?:английск\w*|english)\s+озвучк\w*\b", normalized):
        return "voice_en"
    return None


def clock_display_configuration(value: str | None) -> str | None:
    """Returns an explicit with/without clock or display configuration."""

    if not value:
        return None
    for configuration, pattern in _DISPLAY_CONFIGURATION_PATTERNS:
        if pattern.search(value):
            return configuration
    return None


def product_condition(value: str | None) -> str:
    if not value:
        return "new"
    for condition, pattern in _CONDITION_PATTERNS:
        if pattern.search(value):
            return condition
    return "new"


def bundle_identity(value: str | None) -> BundleIdentity | None:
    if not value:
        return None

    normalized = _normalize(value)
    normalized = re.sub(
        r"\b(?:(?:nano[-\s]?)?sim\s*\+\s*e[-\s]?sim|"
        r"gps\s*\+\s*cellular)\b",
        " ",
        normalized,
    )

    has_bundle = bool(
        re.search(
            r"\s\+\s|\bbundle\b|\bкомплект\w*\s+(?:с|из)\b|"
            r"\bв\s+комплекте\s+с\b|"
            r"\b(?:[2-9]|two|three|два|три)\s+"
            r"(?:controllers?|gamepads?|контроллер\w*|геймпад\w*)\b",
            normalized,
        )
    )
    if not has_bundle:
        return None

    count_match = re.search(
        r"\b([2-9]|two|three|два|три)\s+"
        r"(?:controllers?|gamepads?|контроллер\w*|геймпад\w*)\b",
        normalized,
    )
    count_aliases = {"two": 2, "два": 2, "three": 3, "три": 3}
    count = None
    if count_match is not None:
        raw_count = count_match.group(1)
        count = int(raw_count) if raw_count.isdigit() else count_aliases[raw_count]

    for marker, pattern in _BUNDLE_ITEMS:
        if pattern.search(normalized):
            return BundleIdentity(marker=marker, count=count)
    return BundleIdentity(marker=None, count=count)


def variant_mismatch_reason(
    requested_title: str,
    candidate_title: str,
) -> str | None:
    if product_condition(requested_title) != product_condition(candidate_title):
        return "condition"

    requested_bundle = bundle_identity(requested_title)
    candidate_bundle = bundle_identity(candidate_title)
    if (requested_bundle is None) != (candidate_bundle is None):
        return "bundle"
    if (
        requested_bundle is not None
        and candidate_bundle is not None
        and requested_bundle.marker is not None
        and candidate_bundle.marker is not None
        and requested_bundle != candidate_bundle
    ):
        return "bundle"

    requested_memory = memory_signature(requested_title)
    candidate_memory = memory_signature(candidate_title)
    if requested_memory and not requested_memory.issubset(candidate_memory):
        return "memory"

    requested_device = device_configuration(requested_title)
    candidate_device = device_configuration(candidate_title)
    if requested_device in {"digital", "disc"} or candidate_device in {
        "digital",
        "disc",
    }:
        if requested_device != candidate_device:
            return "configuration"
    elif (
        requested_device is not None
        and candidate_device is not None
        and requested_device != candidate_device
    ):
        return "configuration"

    requested_connector = connector_configuration(requested_title)
    candidate_connector = connector_configuration(candidate_title)
    if (
        requested_connector is not None
        and candidate_connector is not None
        and requested_connector != candidate_connector
    ):
        return "configuration"

    requested_voice = voice_configuration(requested_title)
    candidate_voice = voice_configuration(candidate_title)
    if (
        requested_voice is not None
        and candidate_voice is not None
        and requested_voice != candidate_voice
    ):
        return "configuration"

    requested_display = clock_display_configuration(requested_title)
    candidate_display = clock_display_configuration(candidate_title)
    if (
        requested_display != candidate_display
        and (requested_display is not None or candidate_display is not None)
    ):
        return "configuration"

    requested_region = explicit_region(requested_title)
    candidate_region = explicit_region(candidate_title)
    if (
        requested_region is not None
        and candidate_region is not None
        and requested_region != candidate_region
    ):
        return "region"

    requested_sim = sim_configuration(requested_title)
    candidate_sim = sim_configuration(candidate_title)
    if (
        requested_sim is not None
        and candidate_sim is not None
        and requested_sim != candidate_sim
    ):
        return "sim"

    return None


def neutralize_variant_markers(value: str) -> str:
    result = value
    result = _MEMORY_PAIR_RE.sub(" ", result)
    result = _MEMORY_RE.sub(" ", result)

    for _, pattern in _CONDITION_PATTERNS:
        result = pattern.sub(" ", result)
    for _, pattern in _REGION_PATTERNS:
        result = pattern.sub(" ", result)
    for _, pattern in _DISPLAY_CONFIGURATION_PATTERNS:
        result = pattern.sub(" ", result)
    for pattern in _VARIANT_REMOVERS:
        result = pattern.sub(" ", result)

    result = re.sub(
        r"\s+\+\s+.*$|\bbundle\b.*$|\bкомплект\w*\s+(?:с|из)\b.*$|"
        r"\bв\s+комплекте\s+с\b.*$",
        " ",
        result,
        flags=re.I,
    )
    result = re.sub(r"\(\s*[,;/+-]*\s*\)", " ", result)
    result = re.sub(r"\s+", " ", result)
    return result.strip(" -/,;()")
