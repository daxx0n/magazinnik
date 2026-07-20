from __future__ import annotations

import os
import unicodedata


class SearchInputError(ValueError):
    """Запрос нельзя безопасно отправлять внешним источникам."""


def normalize_search_query(
    value: str,
    *,
    min_length: int = 3,
    max_length: int | None = None,
) -> str:
    """Нормализует Unicode, удаляет управляющие символы и проверяет длину."""

    limit = max_length or _environment_limit()
    normalized = unicodedata.normalize("NFKC", value)
    cleaned = "".join(
        character
        for character in normalized
        if not (
            unicodedata.category(character).startswith("C")
            and character not in {"\t", "\n", "\r"}
        )
    )
    cleaned = " ".join(cleaned.split())

    if len(cleaned) < min_length:
        raise SearchInputError("Название слишком короткое.")
    if len(cleaned) > limit:
        raise SearchInputError(
            f"Название слишком длинное. Максимум: {limit} символов."
        )
    if not any(character.isalnum() for character in cleaned):
        raise SearchInputError("Добавь название или модель товара.")
    return cleaned


def _environment_limit() -> int:
    raw = os.getenv("SEARCH_MAX_QUERY_LENGTH", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return 200
    return value if value >= 20 else 200
