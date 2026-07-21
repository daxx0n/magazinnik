from __future__ import annotations

from pathlib import Path


handler = Path("app/handlers/search.py")
text = handler.read_text(encoding="utf-8")
text = text.replace(
    "    any_callback: str,\n    original_query: str | None = None,",
    "    any_callback: str | None = None,\n    original_query: str | None = None,",
    1,
)
text = text.replace(
    '''    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🎨 Любой — найти дешевле",
            callback_data=any_callback,
        )
    )
    sorted_choices = sorted(
''',
    '''    builder = InlineKeyboardBuilder()
    if any_callback is not None:
        builder.row(
            InlineKeyboardButton(
                text="🎨 Любой — найти дешевле",
                callback_data=any_callback,
            )
        )
    sorted_choices = sorted(
''',
    1,
)
text = text.replace(
    '''        except (ProductNotFoundError, SourceUnavailableError):
            return None
''',
    '''        except (ProductNotFoundError, SourceUnavailableError):
            return None
        except Exception:
            logger.exception(
                "Any-color variant search failed: product=%s",
                product.key,
            )
            return None
''',
    1,
)
handler.write_text(text, encoding="utf-8")

source_statuses = Path("tests/test_source_statuses.py")
test_text = source_statuses.read_text(encoding="utf-8")
test_text = test_text.replace(
    '            "ol:model-10",\n',
    '            "olg:search:10",\n',
    1,
)
source_statuses.write_text(test_text, encoding="utf-8")
