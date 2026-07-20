from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f"Missing replacement target: {label}")


def patch_model_selection() -> None:
    path = ROOT / "app/services/model_selection.py"
    text = path.read_text(encoding="utf-8")
    old = '''    tokens = title.split()
    max_width = min(4, len(tokens) - 1)
'''
    new = '''    tokens = title.split()
    if not tokens:
        return None

    last_token = tokens[-1].strip("()[]{}.,;:-_/ ")
    if not last_token or requested_color_key(last_token) is None:
        # Цвет должен завершать название. Иначе слова после цвета могут быть
        # состоянием товара, комплектом или иной значимой модификацией.
        return None

    max_width = min(4, len(tokens) - 1)
'''
    text = replace_once(text, old, new, "terminal color suffix")
    path.write_text(text, encoding="utf-8")


def patch_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text(encoding="utf-8")
    old = '''        def is_accessory(value: str) -> bool:
            return any(
                token.startswith(marker)
                for token in value.split()
                for marker in accessory_markers
            )
'''
    new = '''        def is_accessory(value: str) -> bool:
            normalized_value = re.sub(
                r"\\b(?:без|с)\\s+дисковод\\w*\\b",
                " ",
                value.casefold().replace("ё", "е"),
            )
            return any(
                token.startswith(marker)
                for token in normalized_value.split()
                for marker in accessory_markers
            )
'''
    text = replace_once(text, old, new, "built-in disc drive configuration")
    path.write_text(text, encoding="utf-8")


def patch_sqlite_catalog_storage() -> None:
    path = ROOT / "app/services/sqlite_catalog_storage.py"
    text = path.read_text(encoding="utf-8")
    if "from contextlib import contextmanager\n" not in text:
        text = text.replace(
            "import sqlite3\n",
            "import sqlite3\nfrom contextlib import contextmanager\n",
            1,
        )
    text = text.replace(
        "with self._connect() as connection:",
        "with self._connection() as connection:",
    )
    text = replace_once(
        text,
        '        connection = self._connect()\n        try:\n            connection.execute("BEGIN IMMEDIATE")\n',
        '        connection = self._connect()\n        try:\n            connection.execute("PRAGMA journal_mode = WAL")\n            connection.execute("PRAGMA synchronous = NORMAL")\n            connection.execute("BEGIN IMMEDIATE")\n',
        "catalog WAL initialization",
    )
    marker = "    def _connect(self) -> sqlite3.Connection:\n"
    context_method = '''    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

'''
    if context_method not in text:
        text = replace_once(
            text,
            marker,
            context_method + marker,
            "catalog connection context",
        )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_model_selection()
    patch_price_service()
    patch_sqlite_catalog_storage()


if __name__ == "__main__":
    main()
