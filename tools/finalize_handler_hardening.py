from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def patch_sessions() -> None:
    path = ROOT / "app/services/search_sessions.py"
    text = path.read_text(encoding="utf-8")
    marker = '''    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
'''
    replacement = '''    def contains(self, session_id: str) -> bool:
        """Проверяет наличие активной записи без изменения LRU."""

        return session_id in self._sessions

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
'''
    if marker in text:
        text = text.replace(marker, replacement, 1)
    elif replacement not in text:
        raise RuntimeError("Missing session remove marker")
    path.write_text(text, encoding="utf-8")


def patch_handler() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text(encoding="utf-8")

    comparison_pattern = re.compile(
        r"async def load_product_comparison\(.*?"
        r"(?=@router\.callback_query\(\n    F\.data\.startswith\(\"olp:\"\)\n\))",
        re.DOTALL,
    )
    comparison_block = '''async def load_product_comparison(
    message: Message,
    product_key: str,
    original_query: str | None = None,
    user_id: int | None = None,
) -> None:
    """Загружает сравнение и пишет один снимок на общую coalesced-задачу."""

    await message.edit_text(
        "🔎 Сравниваю цены Onliner, 21vek, "
        "5 элемента, Shop.by, Электросилы и Zeon..."
    )

    async def fetch_and_record() -> ComparisonResult:
        result = await price_service.search_all_sources_by_onliner_key(
            product_key,
            original_query=None,
        )
        display_title = (
            result.master_product_title
            or result.product_title
        )
        try:
            await asyncio.to_thread(
                get_price_history_repository().record_offers,
                product_key,
                display_title,
                result.offers,
            )
        except Exception:
            logger.exception(
                "Price history write failed: product=%s",
                product_key,
            )
        return result

    try:
        comparison = await comparison_coordinator.run(
            (product_key, ""),
            fetch_and_record,
        )
        if original_query:
            comparison = replace(
                comparison,
                query=original_query,
            )
    except SearchBusyError:
        await message.edit_text(
            "Сейчас выполняется слишком много сравнений. "
            "Попробуй ещё раз через несколько секунд."
        )
        return
    except ProductNotFoundError as error:
        await message.edit_text(
            f"Предложения не найдены.\\n\\n{error}"
        )
        return
    except SourceUnavailableError as error:
        logger.warning(
            "Aggregate search unavailable: %s",
            error,
        )
        await message.edit_text(
            "Не удалось получить данные "
            "для выбранной модели.\\n"
            "Попробуй повторить запрос."
        )
        return
    except Exception:
        logger.exception("Unexpected product selection error")
        await message.edit_text("Произошла непредвиденная ошибка.")
        return

    chat_id = message_chat_id(message)
    if chat_id is not None:
        store_comparison_diagnostics(
            chat_id=chat_id,
            user_id=user_id,
            comparison=comparison,
        )

    await show_comparison(
        message=message,
        offers=comparison.offers,
        source_statuses=comparison.source_statuses,
        product_key=product_key,
        product_title=(
            comparison.master_product_title
            if comparison.catalog_presentation
            else None
        ),
        grouped=comparison.catalog_presentation,
    )


'''
    text, count = comparison_pattern.subn(comparison_block, text, count=1)
    if count != 1:
        raise RuntimeError("Unable to normalize comparison loader")

    helper_pattern = re.compile(
        r"\ndef callback_user_id\(.*?"
        r"(?=\ndef store_comparison_diagnostics\()",
        re.DOTALL,
    )
    helper_block = '''
def callback_user_id(callback: CallbackQuery) -> int | None:
    user = getattr(callback, "from_user", None)
    user_id = getattr(user, "id", None)
    return user_id if isinstance(user_id, int) else None


def message_user_id(message: Message) -> int | None:
    user = getattr(message, "from_user", None)
    user_id = getattr(user, "id", None)
    return user_id if isinstance(user_id, int) else None


def message_interaction_key(
    message: Message,
) -> tuple[int, int | None] | None:
    chat_id = message_chat_id(message)
    if chat_id is None:
        return None
    return chat_id, message_user_id(message)


def authorized_product_search(
    callback: CallbackQuery,
    search_id: str,
) -> list[ProductCandidate] | None:
    metadata = product_session_registry.authorize(
        search_id,
        chat_id=(
            message_chat_id(callback.message)
            if callback.message is not None
            else None
        ),
        user_id=callback_user_id(callback),
    )
    products = product_searches.get(search_id)
    if metadata is None:
        if not product_session_registry.contains(search_id):
            product_searches.pop(search_id, None)
            product_search_parents.pop(search_id, None)
        return None
    if products is None:
        product_search_parents.pop(search_id, None)
        product_session_registry.remove(search_id)
        return None
    product_searches.move_to_end(search_id)
    return products


def authorized_category_search(
    callback: CallbackQuery,
    search_id: str,
) -> CategorySearchSession | None:
    metadata = category_session_registry.authorize(
        search_id,
        chat_id=(
            message_chat_id(callback.message)
            if callback.message is not None
            else None
        ),
        user_id=callback_user_id(callback),
    )
    session = category_searches.get(search_id)
    if metadata is None:
        if not category_session_registry.contains(search_id):
            category_searches.pop(search_id, None)
        return None
    if session is None:
        category_session_registry.remove(search_id)
        return None
    category_searches.move_to_end(search_id)
    return session


'''
    text, count = helper_pattern.subn(helper_block, text, count=1)
    if count != 1:
        raise RuntimeError("Unable to normalize callback helpers")

    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_sessions()
    patch_handler()


if __name__ == "__main__":
    main()
