"""Conservative fallback for store titles that omit manufacturer model codes."""

from __future__ import annotations

import re

from app.services.variant_matching import memory_signature


_SEPARATED_CODE_RE = re.compile(
    r"[a-zа-я0-9]+(?:[-_/.][a-zа-я0-9]+)+",
    re.IGNORECASE,
)
_MEMORY_PAIR_RE = re.compile(
    r"\d{1,4}\s*(?:gb|tb|mb|гб|тб|мб)?\s*[/_-]\s*"
    r"\d{1,4}\s*(?:gb|tb|mb|гб|тб|мб)?",
    re.IGNORECASE,
)
_MEMORY_TOKEN_RE = re.compile(
    r"\d+(?:gb|tb|mb|гб|тб|мб)",
    re.IGNORECASE,
)
_IGNORED_SHORT_CODES = {
    "2sim",
    "3g",
    "4g",
    "5g",
    "esim",
    "lte",
}


def _normalize(value: str) -> str:
    return value.casefold().replace("ё", "е")


def _is_alphanumeric_code(value: str, *, minimum_length: int) -> bool:
    return (
        len(value) >= minimum_length
        and re.search(r"[a-zа-я]", value) is not None
        and re.search(r"\d", value) is not None
    )


def _separated_long_codes(value: str) -> tuple[set[str], set[str]]:
    codes: set[str] = set()
    parts: set[str] = set()

    for raw_code in _SEPARATED_CODE_RE.findall(_normalize(value)):
        if _MEMORY_PAIR_RE.fullmatch(raw_code) is not None:
            continue

        compact = re.sub(r"[^a-zа-я0-9]", "", raw_code)
        if not _is_alphanumeric_code(compact, minimum_length=4):
            continue

        codes.add(compact)
        parts.update(re.findall(r"[a-zа-я0-9]+", raw_code))

    return codes, parts


def explicit_long_model_codes(value: str) -> set[str]:
    """Returns explicit long codes such as GFY-LX1 or SM-S931B."""

    normalized = _normalize(value)
    codes, _ = _separated_long_codes(normalized)

    for token in re.findall(r"[a-zа-я0-9]+", normalized):
        if _MEMORY_TOKEN_RE.fullmatch(token) is not None:
            continue
        if _is_alphanumeric_code(token, minimum_length=4):
            codes.add(token)

    return codes


def short_marketing_model_codes(value: str) -> set[str]:
    """Returns compact marketing model tokens such as Y63, A55, or S24."""

    normalized = _normalize(value)
    _, long_code_parts = _separated_long_codes(normalized)
    result: set[str] = set()

    for token in re.findall(r"[a-zа-я0-9]+", normalized):
        if token in long_code_parts:
            continue
        if token in _IGNORED_SHORT_CODES:
            continue
        if _MEMORY_TOKEN_RE.fullmatch(token) is not None:
            continue
        if 2 <= len(token) <= 4 and _is_alphanumeric_code(
            token,
            minimum_length=2,
        ):
            result.add(token)

    return result


def allows_omitted_model_code(
    requested_title: str,
    candidate_title: str,
) -> bool:
    """Allows a missing long code only with exact memory and short model token.

    A candidate with another explicit long code is never accepted by this
    fallback. This keeps conflicting regional or hardware codes strict while
    allowing retailers that publish only the marketing model name.
    """

    requested_long_codes = explicit_long_model_codes(requested_title)
    candidate_long_codes = explicit_long_model_codes(candidate_title)

    if not requested_long_codes or candidate_long_codes:
        return False

    requested_memory = memory_signature(requested_title)
    candidate_memory = memory_signature(candidate_title)
    if (
        not requested_memory
        or requested_memory != candidate_memory
    ):
        return False

    requested_short_codes = short_marketing_model_codes(requested_title)
    candidate_short_codes = short_marketing_model_codes(candidate_title)

    return bool(
        requested_short_codes
        and requested_short_codes.issubset(candidate_short_codes)
    )
