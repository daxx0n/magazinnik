"""Shared normalization rules for catalog identity and live matching."""

from __future__ import annotations

import re


_REGIONAL_MODEL_SUFFIX = re.compile(
    r"(?<![a-zа-я0-9])"
    r"([a-zа-я0-9-]{6,})\s*/\s*"
    r"(?:lp|ru|by|eu|ua|kz|s[0-9]|[a-z]{2,3})"
    r"(?![a-zа-я0-9])",
    re.IGNORECASE,
)


def strip_regional_model_suffixes(value: str) -> str:
    """Removes distribution-region suffixes without changing the model."""

    return _REGIONAL_MODEL_SUFFIX.sub(r"\1", value)
