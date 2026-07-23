import asyncio
import logging
import os
import secrets
from collections import Counter, OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import (
    InlineKeyboardBuilder,
)

from app.models.category import ProductCategory
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import (
    ComparisonResult,
    SourceSearchStatus,
)
from app.services.any_color import (
    aggregate_any_color_results,
    load_any_color_results,
)
from app.services.model_selection import (
    group_model_variants,
    requested_color_key,
    selected_color_label,
)
from app.services.price_service import PriceService
from app.services.price_history import PriceHistoryRepository
from app.services.search_input import SearchInputError, normalize_search_query
from app.services.search_load import (
    SearchBusyError,
    SearchRequestCoordinator,
)
from app.services.search_sessions import (
    SearchSessionRegistry,
    SelectionQueryRegistry,
)
from app.services.selection_flow import (
    has_memory_choice,
    ordered_memory_groups,
    ordered_variant_groups,
    selectable_memory_groups,
)
from app.services.product_variants import (
    ProductVariantGroup,
    display_color,
    display_product_title,
    extract_memory,
    group_by_memory,
)
from app.sources import (
    InvalidProductUrlError,
    ProductNotFoundError,
    SourceUnavailableError,
)


router = Router(name="search")

price_service = PriceService()

logger = logging.getLogger(__name__)

PRODUCT_PAGE_SIZE = 10
CATEGORY_PAGE_SIZE = 10
MAX_SEARCH_SESSIONS = 1_000
MAX_DIAGNOSTIC_SESSIONS = 1_000
SEARCH_SESSION_TTL_SECONDS = 1_800.0
product_searches: OrderedDict[
    str,
    list[ProductCandidate],
] = OrderedDict()
product_search_parents: dict[
    str,
    tuple[str, int],
] = {}


@dataclass(frozen=True, slots=True)
class CategorySearchSession:
    """Широкий запрос и найденные для него разделы."""

    query: str
    categories: list[ProductCategory]


category_searches: OrderedDict[
    str,
    CategorySearchSession,
] = OrderedDict()
comparison_diagnostics: OrderedDict[
    tuple[int, int | None],
    ComparisonResult,
] = OrderedDict()
price_history_repository: PriceHistoryRepository | None = None
product_session_registry = SearchSessionRegistry(
    capacity=MAX_SEARCH_SESSIONS,
    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,
)
category_session_registry = SearchSessionRegistry(
    capacity=MAX_SEARCH_SESSIONS,
    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,
)
selection_query_registry = SelectionQueryRegistry(
    capacity=10_000,
    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,
)
comparison_coordinator: SearchRequestCoordinator[
    tuple[str, str],
    ComparisonResult,
] = SearchRequestCoordinator()
category_discovery_coordinator: SearchRequestCoordinator[
    str,
    list[ProductCategory],
] = SearchRequestCoordinator()
product_discovery_coordinator: SearchRequestCoordinator[
    tuple[str, str],
    list[ProductCandidate],
] = SearchRequestCoordinator()



def initialize_price_history(database_path: str | None = None) -> None:
    """Подключает постоянное хранилище цен и подписок."""

    global price_history_repository
    price_history_repository = PriceHistoryRepository(
        database_path
        or os.getenv(
            "PRICE_DATABASE_PATH",
            "data/magazinnik.sqlite3",
        )
    )
    price_history_repository.initialize()


def get_price_history_repository() -> PriceHistoryRepository:
    global price_history_repository

    if price_history_repository is None:
        initialize_price_history()

    assert price_history_repository is not None
    return price_history_repository


@router.message(Command("diagnostics", "debug"))
async def handle_diagnostics(message: Message) -> None:
    """Показывает диагностику последнего сравнения в чате."""

    interaction_key = message_interaction_key(message)
    comparison = (
        comparison_diagnostics.get(interaction_key)
        if interaction_key is not None
        else None
    )

    if comparison is None:
        await message.answer(
            "Диагностики пока нет.\n\n"
            "Сначала выбери конкретный товар и дождись "
            "сравнения цен."
        )
        return

    await message.answer(
        format_comparison_diagnostics(comparison),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("price_history:"))
async def handle_price_history(callback: CallbackQuery) -> None:
    """Показывает последние минимальные цены товара."""

    await callback.answer()

    if callback.message is None:
        return

    product_key = (callback.data or "").removeprefix(
        "price_history:"
    )
    points = await asyncio.to_thread(
        get_price_history_repository().history,
        product_key,
        10,
    )

    if not points:
        await callback.message.answer(
            "История для этого товара пока не накоплена."
        )
        return

    lines = ["📉 История минимальной цены", ""]

    for point in points:
        try:
            observed_at = datetime.fromisoformat(
                point.observed_at
            ).astimezone().strftime("%d.%m.%Y %H:%M")
        except ValueError:
            observed_at = point.observed_at

        lines.append(
            f"• {observed_at}: {point.price:.2f} "
            f"{point.currency} — {point.source}"
        )

    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("price_alert:"))
async def handle_price_alert(callback: CallbackQuery) -> None:
    """Включает или отключает уведомления о снижении цены."""

    if callback.message is None:
        await callback.answer()
        return

    chat_id = message_chat_id(callback.message)
    user_id = callback_user_id(callback)
    product_key = (callback.data or "").removeprefix(
        "price_alert:"
    )
    comparison = (
        comparison_diagnostics.get((chat_id, user_id))
        if chat_id is not None
        else None
    )

    if (
        chat_id is None
        or comparison is None
        or comparison.product_key != product_key
        or not comparison.offers
    ):
        await callback.answer(
            "Сравнение устарело — выбери товар ещё раз.",
            show_alert=True,
        )
        return

    cheapest = comparison.offers[0]
    enabled = await asyncio.to_thread(
        get_price_history_repository().toggle_alert,
        chat_id,
        product_key,
        (
            comparison.master_product_title
            or comparison.product_title
            or cheapest.title
        ),
        comparison.query or comparison.product_title,
        float(cheapest.price),
        cheapest.currency,
    )
    await callback.answer(
        (
            "Уведомление включено. Сообщу, когда цена станет ниже."
            if enabled
            else "Уведомление отключено."
        ),
        show_alert=True,
    )


@router.message(Command("onliner"))
async def handle_onliner_url(
    message: Message,
) -> None:
    """Обрабатывает прямую ссылку Onliner."""

    command_text = message.text or ""

    command_parts = command_text.split(
        maxsplit=1
    )

    if len(command_parts) < 2:
        await message.answer(
            "После команды отправь ссылку "
            "на товар Onliner.\n\n"
            "Пример:\n"
            "/onliner "
            "https://catalog.onliner.by/"
            "mobile/apple/iphone17256bk"
        )
        return

    product_url = command_parts[1].strip()

    status_message = await message.answer(
        "🔎 Получаю предложения Onliner..."
    )

    try:
        offers = (
            await price_service.search_onliner_url(
                product_url
            )
        )
    except InvalidProductUrlError as error:
        await status_message.edit_text(
            f"Некорректная ссылка.\n\n{error}"
        )
        return
    except ProductNotFoundError as error:
        await status_message.edit_text(
            f"Товар не найден.\n\n{error}"
        )
        return
    except SourceUnavailableError as error:
        logger.warning(
            "Onliner unavailable: %s",
            error,
        )

        await status_message.edit_text(
            "Onliner временно недоступен.\n"
            "Попробуй повторить запрос."
        )
        return
    except Exception:
        logger.exception(
            "Unexpected Onliner error"
        )

        await status_message.edit_text(
            "Произошла непредвиденная ошибка."
        )
        return

    await show_offers(
        message=status_message,
        offers=offers,
    )

@router.message(Command("five"))
async def handle_five_element_url(
    message: Message,
) -> None:
    """Обрабатывает ссылку 5element.by."""

    command_text = message.text or ""

    command_parts = command_text.split(
        maxsplit=1
    )

    if len(command_parts) < 2:
        await message.answer(
            "После команды отправь ссылку "
            "на товар 5 элемента.\n\n"
            "Пример:\n"
            "/five "
            "https://5element.by/products/"
            "iphone-17-256gb-black-"
            "telefon-gsm-apple-mg6j4hn-a"
        )
        return

    product_url = command_parts[1].strip()

    status_message = await message.answer(
        "🔎 Получаю цену из 5 элемента..."
    )

    try:
        offers = (
            await price_service
            .search_five_element_url(
                product_url
            )
        )

    except InvalidProductUrlError as error:
        await status_message.edit_text(
            f"Некорректная ссылка.\n\n{error}"
        )
        return

    except ProductNotFoundError as error:
        await status_message.edit_text(
            f"Товар не найден.\n\n{error}"
        )
        return

    except SourceUnavailableError as error:
        logger.warning(
            "5element unavailable: %s",
            error,
        )

        await status_message.edit_text(
            "5 элемент временно недоступен."
        )
        return

    except Exception:
        logger.exception(
            "Unexpected 5element error"
        )

        await status_message.edit_text(
            "Произошла ошибка при получении "
            "данных из 5 элемента."
        )
        return

    await show_offers(
        message=status_message,
        offers=offers,
    )

@router.message(Command("compare"))
async def handle_compare(
    message: Message,
) -> None:
    """Сравнивает Onliner и 5 элемент."""

    command_text = message.text or ""

    command_parts = command_text.split()

    if len(command_parts) != 3:
        await message.answer(
            "Команда должна содержать "
            "две ссылки:\n\n"
            "/compare "
            "ССЫЛКА_ONLINER "
            "ССЫЛКА_5ELEMENT"
        )
        return

    onliner_url = command_parts[1]
    five_element_url = command_parts[2]

    status_message = await message.answer(
        "🔎 Сравниваю Onliner "
        "и 5 элемент..."
    )

    try:
        offers = (
            await price_service.compare_urls(
                onliner_url=onliner_url,
                five_element_url=(
                    five_element_url
                ),
            )
        )

    except InvalidProductUrlError as error:
        await status_message.edit_text(
            f"Некорректная ссылка.\n\n{error}"
        )
        return

    except ProductNotFoundError as error:
        await status_message.edit_text(
            f"Не удалось получить товар.\n\n"
            f"{error}"
        )
        return

    except SourceUnavailableError as error:
        logger.warning(
            "Compare source unavailable: %s",
            error,
        )

        await status_message.edit_text(
            "Один из магазинов временно "
            "недоступен."
        )
        return

    except Exception:
        logger.exception(
            "Unexpected comparison error"
        )

        await status_message.edit_text(
            "Произошла ошибка "
            "при сравнении цен."
        )
        return

    await show_comparison(
        message=status_message,
        offers=offers,
    )

@router.callback_query(
    F.data.startswith("ol:")
)
async def handle_product_selection(
    callback: CallbackQuery,
) -> None:
    """Загружает цены выбранной карточки."""

    await callback.answer()

    if callback.message is None:
        return

    product_key = (callback.data or "").removeprefix(
        "ol:"
    )

    chat_id = message_chat_id(callback.message)
    user_id = callback_user_id(callback)
    original_query = selection_query_registry.get(
        chat_id=chat_id,
        user_id=user_id,
        product_key=product_key,
    )
    await load_product_comparison(
        message=callback.message,
        product_key=product_key,
        original_query=original_query,
        user_id=user_id,
    )


async def load_product_comparison(
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
            f"Предложения не найдены.\n\n{error}"
        )
        return
    except SourceUnavailableError as error:
        logger.warning(
            "Aggregate search unavailable: %s",
            error,
        )
        await message.edit_text(
            "Не удалось получить данные "
            "для выбранной модели.\n"
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


@router.callback_query(
    F.data.startswith("olp:")
)
async def handle_product_page(
    callback: CallbackQuery,
) -> None:
    """Переключает страницу найденных моделей."""

    await callback.answer()

    if callback.message is None:
        return

    callback_parts = (callback.data or "").split(":")

    if len(callback_parts) != 3:
        return

    _, search_id, raw_page = callback_parts
    products = authorized_product_search(callback, search_id)

    if products is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. "
            "Повтори запрос."
        )
        return

    try:
        page = int(raw_page)
    except ValueError:
        return

    groups = ordered_variant_groups(products, group_model_variants)
    max_page = (len(groups) - 1) // PRODUCT_PAGE_SIZE
    page = min(max(page, 0), max_page)

    await callback.message.edit_text(
        format_product_page_text(
            total=len(groups),
            page=page,
        ),
        reply_markup=build_product_keyboard(
            products=products,
            search_id=search_id,
            page=page,
        ),
    )


@router.callback_query(
    F.data.startswith("olcp:")
)
async def handle_category_page(
    callback: CallbackQuery,
) -> None:
    """Переключает страницы товарных категорий."""

    await callback.answer()

    if callback.message is None:
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 3:
        return

    _, search_id, raw_page = parts
    session = authorized_category_search(callback, search_id)

    if session is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. Повтори запрос."
        )
        return

    try:
        page = int(raw_page)
    except ValueError:
        return

    max_page = (
        len(session.categories) - 1
    ) // CATEGORY_PAGE_SIZE
    page = min(max(page, 0), max_page)

    await callback.message.edit_text(
        format_category_page_text(
            query=session.query,
            total=len(session.categories),
            page=page,
        ),
        reply_markup=build_category_keyboard(
            categories=session.categories,
            search_id=search_id,
            page=page,
        ),
    )


@router.callback_query(
    F.data.startswith("olc:")
)
async def handle_category_selection(
    callback: CallbackQuery,
) -> None:
    """Загружает модели выбранной категории."""

    await callback.answer()

    if callback.message is None:
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 3:
        return

    _, category_search_id, raw_category_index = parts
    session = authorized_category_search(
        callback,
        category_search_id,
    )

    if session is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. Повтори запрос."
        )
        return

    try:
        category_index = int(raw_category_index)
        category = session.categories[category_index]
    except (ValueError, IndexError):
        return

    await callback.message.edit_text(
        f"🔎 Ищу {session.query} в категории "
        f"«{category.title}»..."
    )

    try:
        products = await product_discovery_coordinator.run(
            (session.query.casefold(), category.key),
            lambda: price_service.find_onliner_products(
                query=session.query,
                category=category.key,
            ),
        )
    except SearchBusyError:
        await callback.message.edit_text(
            "Сейчас выполняется слишком много поисков. "
            "Попробуй ещё раз через несколько секунд."
        )
        return
    except SourceUnavailableError as error:
        logger.warning(
            "Onliner category search unavailable: %s",
            error,
        )
        await callback.message.edit_text(
            "Поиск Onliner временно недоступен."
        )
        return
    except Exception:
        logger.exception("Unexpected category search error")
        await callback.message.edit_text(
            "Произошла ошибка при поиске."
        )
        return

    category_page = category_index // CATEGORY_PAGE_SIZE

    if not products:
        await callback.message.edit_text(
            "В этой категории подходящие товары не найдены.",
            reply_markup=build_category_back_keyboard(
                category_search_id,
                category_page,
            ),
        )
        return

    search_id = store_product_search(
        products,
        parent=(category_search_id, category_page),
        query=session.query,
        owner_chat_id=message_chat_id(callback.message),
        owner_user_id=callback_user_id(callback),
    )
    groups = ordered_variant_groups(products, group_model_variants)

    await callback.message.edit_text(
        f"Категория: {category.title}\n\n"
        + format_product_page_text(
            total=len(groups),
            page=0,
        ),
        reply_markup=build_product_keyboard(
            products=products,
            search_id=search_id,
            page=0,
        ),
    )


@router.callback_query(
    F.data.startswith("olg:")
)
async def handle_variant_group(
    callback: CallbackQuery,
) -> None:
    """Shows memory only when the selected model has real memory variants."""

    await callback.answer()

    if callback.message is None:
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 3:
        return

    _, search_id, raw_group_index = parts
    products = authorized_product_search(callback, search_id)

    if products is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. "
            "Повтори запрос."
        )
        return

    try:
        group_index = int(raw_group_index)
        group = ordered_variant_groups(products, group_model_variants)[
            group_index
        ]
    except (ValueError, IndexError):
        return

    if not group.products:
        return

    if not has_memory_choice(group.products):
        user_id = callback_user_id(callback)
        original_query = selection_query_registry.get(
            chat_id=message_chat_id(callback.message),
            user_id=user_id,
            product_key=group.products[0].key,
        )
        await show_color_selection(
            message=callback.message,
            group=group,
            products=group.products,
            back_callback=(
                f"olp:{search_id}:"
                f"{group_index // PRODUCT_PAGE_SIZE}"
            ),
            any_callback=f"ola:{search_id}:{group_index}:all",
            original_query=original_query,
            user_id=user_id,
            memory_selected=False,
        )
        return

    memory_groups = selectable_memory_groups(group.products)
    await callback.message.edit_text(
        f"🏷️ {group.title}\n\nВыбери память:",
        reply_markup=build_memory_keyboard(
            search_id=search_id,
            group_index=group_index,
            memory_groups=memory_groups,
        ),
    )

@router.callback_query(
    F.data.startswith("olm:")
)
async def handle_memory_selection(
    callback: CallbackQuery,
) -> None:
    """Показывает цвета выбранной памяти."""

    await callback.answer()

    if callback.message is None:
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 4:
        return

    _, search_id, raw_group_index, raw_memory_index = parts
    products = authorized_product_search(callback, search_id)

    if products is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. "
            "Повтори запрос."
        )
        return

    try:
        group_index = int(raw_group_index)
        memory_index = int(raw_memory_index)
        group = ordered_variant_groups(products, group_model_variants)[
            group_index
        ]
        memory_products = selectable_memory_groups(group.products)[memory_index][1]
    except (ValueError, IndexError):
        return

    user_id = callback_user_id(callback)
    original_query = selection_query_registry.get(
        chat_id=message_chat_id(callback.message),
        user_id=user_id,
        product_key=memory_products[0].key,
    )
    await show_color_selection(
        message=callback.message,
        group=group,
        products=memory_products,
        back_callback=f"olg:{search_id}:{group_index}",
        any_callback=(
            f"ola:{search_id}:{group_index}:{memory_index}"
        ),
        original_query=original_query,
        user_id=user_id,
    )



@router.callback_query(F.data.startswith("ola:"))
async def handle_any_color_selection(callback: CallbackQuery) -> None:
    """Searches the lowest price among all colors of the selected variant."""

    await callback.answer()
    if callback.message is None:
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return


    _, search_id, raw_group_index, raw_memory_index = parts
    products = authorized_product_search(callback, search_id)
    if products is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. Повтори запрос."
        )
        return


    try:
        group_index = int(raw_group_index)
        group = ordered_variant_groups(
            products,
            group_model_variants,
        )[group_index]
        if raw_memory_index == "all":
            memory_products = group.products
        else:
            memory_index = int(raw_memory_index)
            memory_products = selectable_memory_groups(
                group.products
            )[memory_index][1]
    except (ValueError, IndexError):
        return

    if not memory_products:
        return

    user_id = callback_user_id(callback)
    original_query = selection_query_registry.get(
        chat_id=message_chat_id(callback.message),
        user_id=user_id,
        product_key=memory_products[0].key,
    )
    await load_any_color_comparison(
        message=callback.message,
        products=memory_products,
        original_query=original_query,
        user_id=user_id,
    )

async def load_any_color_comparison(
    message: Message,
    products: list[ProductCandidate],
    original_query: str | None,
    user_id: int | None,
) -> None:
    """Объединяет предложения всех цветов и сортирует по цене."""

    await message.edit_text(
        "🔎 Ищу минимальную цену среди всех цветов..."
    )

    async def load(product: ProductCandidate) -> ComparisonResult | None:
        try:
            return await price_service.search_all_sources_by_onliner_key(
                product.key,
                original_query=None,
            )
        except (ProductNotFoundError, SourceUnavailableError):
            return None

    results = await load_any_color_results(products, load)
    comparison = aggregate_any_color_results(
        results,
        original_query=original_query,
    )
    if comparison is None:
        await message.edit_text("Предложения для выбранного варианта не найдены.")
        return

    offers = comparison.offers
    product_key = comparison.product_key or products[0].key

    chat_id = message_chat_id(message)
    if chat_id is not None:
        store_comparison_diagnostics(
            chat_id=chat_id,
            user_id=user_id,
            comparison=comparison,
        )
    try:
        await asyncio.to_thread(
            get_price_history_repository().record_offers,
            product_key,
            comparison.product_title,
            offers,
        )
    except Exception:
        logger.exception("Any-color history write failed")

    await show_comparison(
        message=message,
        offers=offers,
        source_statuses=comparison.source_statuses,
        product_key=product_key,
        product_title=None,
        grouped=False,
    )


@router.message(Command("five_search"))
async def handle_five_element_search(
    message: Message,
) -> None:
    """Ищет товары 5 элемента по названию."""

    command_text = message.text or ""

    command_parts = command_text.split(
        maxsplit=1
    )

    if len(command_parts) < 2:
        await message.answer(
            "После команды введи "
            "название товара.\n\n"
            "Пример:\n"
            "/five_search iPhone 17 256GB"
        )
        return

    try:
        query = normalize_search_query(command_parts[1])
    except SearchInputError as error:
        await message.answer(str(error))
        return

    status_message = await message.answer(
        "🔎 Ищу товары в 5 элементе..."
    )

    try:
        products = (
            await price_service
            .find_five_element_products(
                query
            )
        )

    except SourceUnavailableError as error:
        logger.warning(
            "5element search unavailable: %s",
            error,
        )

        await status_message.edit_text(
            "Поиск 5 элемента недоступен.\n\n"
            f"{error}"
        )
        return

    except Exception:
        logger.exception(
            "Unexpected 5element search error"
        )

        await status_message.edit_text(
            "Произошла ошибка при поиске."
        )
        return

    if not products:
        await status_message.edit_text(
            "Подходящие товары "
            "в 5 элементе не найдены."
        )
        return

    keyboard = (
        build_five_element_keyboard(
            products
        )
    )

    await status_message.edit_text(
        "Нашёл несколько вариантов "
        "в 5 элементе.\n\n"
        "Выбери точную модель:",
        reply_markup=keyboard,
    )

@router.callback_query(
    F.data.startswith("fe:")
)
async def handle_five_element_selection(
    callback: CallbackQuery,
) -> None:
    """Получает цену выбранного товара."""

    await callback.answer()

    if callback.message is None:
        return

    callback_data = callback.data or ""

    product_key = callback_data.removeprefix(
        "fe:"
    )

    await callback.message.edit_text(
        "🔎 Получаю актуальную цену "
        "из 5 элемента..."
    )

    try:
        offers = (
            await price_service
            .search_five_element_key(
                product_key
            )
        )

    except ProductNotFoundError as error:
        await callback.message.edit_text(
            f"Товар не найден.\n\n{error}"
        )
        return

    except SourceUnavailableError as error:
        logger.warning(
            "5element unavailable: %s",
            error,
        )

        await callback.message.edit_text(
            "5 элемент временно недоступен."
        )
        return

    except Exception:
        logger.exception(
            "Unexpected 5element "
            "selection error"
        )

        await callback.message.edit_text(
            "Произошла ошибка при получении "
            "цены из 5 элемента."
        )
        return

    await show_offers(
        message=callback.message,
        offers=offers,
    )

@router.message(Command("twentyone"))
async def handle_twenty_one_vek_url(
    message: Message,
) -> None:
    """Обрабатывает ссылку 21vek.by."""

    command_text = message.text or ""

    command_parts = command_text.split(
        maxsplit=1
    )

    if len(command_parts) < 2:
        await message.answer(
            "После команды отправь ссылку "
            "на товар 21vek.\n\n"
            "Пример:\n"
            "/twentyone "
            "https://www.21vek.by/mobile/"
            "iphone17256gb_apple_10019135.html"
        )
        return

    product_url = command_parts[1].strip()

    status_message = await message.answer(
        "🔎 Получаю цену из 21vek..."
    )

    try:
        offers = (
            await price_service
            .search_twenty_one_vek_url(
                product_url
            )
        )

    except InvalidProductUrlError as error:
        await status_message.edit_text(
            f"Некорректная ссылка.\n\n{error}"
        )
        return

    except ProductNotFoundError as error:
        await status_message.edit_text(
            f"Товар не найден.\n\n{error}"
        )
        return

    except SourceUnavailableError as error:
        logger.warning(
            "21vek unavailable: %s",
            error,
        )

        await status_message.edit_text(
            "21vek временно недоступен."
        )
        return

    except Exception:
        logger.exception(
            "Unexpected 21vek error"
        )

        await status_message.edit_text(
            "Произошла ошибка при получении "
            "данных из 21vek."
        )
        return

    await show_offers(
        message=status_message,
        offers=offers,
    )


@router.message(F.text)
async def handle_search(
    message: Message,
) -> None:
    """Ищет товар по обычному тексту."""

    raw_query = (message.text or "").strip()

    if raw_query.startswith("/"):
        await message.answer(
            "Неизвестная команда.\n"
            "Используй /help."
        )
        return

    try:
        query = normalize_search_query(raw_query)
    except SearchInputError as error:
        await message.answer(str(error))
        return

    status_message = await message.answer(
        "🔎 Ищу подходящие товары..."
    )

    try:
        categories: list[ProductCategory] = []

        if price_service.should_categorize_query(query):
            categories = (
                await category_discovery_coordinator.run(
                    query.casefold(),
                    lambda: price_service.find_onliner_categories(query),
                )
            )

        if len(categories) > 1:
            category_search_id = store_category_search(
                query=query,
                categories=categories,
                owner_chat_id=message_chat_id(message),
                owner_user_id=message_user_id(message),
            )
            await status_message.edit_text(
                format_category_page_text(
                    query=query,
                    total=len(categories),
                    page=0,
                ),
                reply_markup=build_category_keyboard(
                    categories=categories,
                    search_id=category_search_id,
                    page=0,
                ),
            )
            return

        selected_category = (
            categories[0].key
            if len(categories) == 1
            else None
        )
        products = await product_discovery_coordinator.run(
            (query.casefold(), selected_category or ""),
            lambda: price_service.find_onliner_products(
                query,
                category=selected_category,
            ),
        )
    except SearchBusyError:
        await status_message.edit_text(
            "Сейчас выполняется слишком много поисков. "
            "Попробуй ещё раз через несколько секунд."
        )
        return
    except SourceUnavailableError as error:
        logger.warning(
            "Onliner search unavailable: %s",
            error,
        )

        await status_message.edit_text(
            "Поиск Onliner временно недоступен."
        )
        return
    except Exception:
        logger.exception(
            "Unexpected product search error"
        )

        await status_message.edit_text(
            "Произошла ошибка при поиске."
        )
        return

    if not products:
        await status_message.edit_text(
            "Подходящие товары не найдены.\n\n"
            "Попробуй точнее указать модель, "
            "память и производителя."
        )
        return

    search_id = store_product_search(
        products,
        query=query,
        owner_chat_id=message_chat_id(message),
        owner_user_id=message_user_id(message),
    )
    groups = ordered_variant_groups(products, group_model_variants)
    keyboard = build_product_keyboard(
        products=products,
        search_id=search_id,
        page=0,
    )

    await status_message.edit_text(
        format_product_page_text(
            total=len(groups),
            page=0,
        ),
        reply_markup=keyboard,
    )


def build_product_keyboard(
    products: list[ProductCandidate],
    search_id: str,
    page: int,
) -> InlineKeyboardMarkup:
    """Создаёт страницу кнопок выбора товара."""

    builder = InlineKeyboardBuilder()
    groups = ordered_variant_groups(products, group_model_variants)
    start = page * PRODUCT_PAGE_SIZE
    end = start + PRODUCT_PAGE_SIZE

    for group_index, group in enumerate(
        groups[start:end],
        start=start,
    ):
        button_text = group.title

        if len(button_text) > 58:
            button_text = (
                button_text[:55] + "..."
            )

        callback_data = f"olg:{search_id}:{group_index}"

        builder.row(
            InlineKeyboardButton(
                text=button_text,
                callback_data=callback_data,
            )
        )

    navigation: list[InlineKeyboardButton] = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⏮ В начало",
                callback_data=f"olp:{search_id}:0",
            )
        )
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=(
                    f"olp:{search_id}:{page - 1}"
                ),
            )
        )

    if end < len(groups):
        navigation.append(
            InlineKeyboardButton(
                text="Далее ➡️",
                callback_data=(
                    f"olp:{search_id}:{page + 1}"
                ),
            )
        )

    if navigation:
        builder.row(*navigation)

    parent = product_search_parents.get(search_id)

    if parent is not None:
        category_search_id, category_page = parent
        builder.row(
            InlineKeyboardButton(
                text="⬅️ К категориям",
                callback_data=(
                    f"olcp:{category_search_id}:"
                    f"{category_page}"
                ),
            )
        )

    return builder.as_markup()


def build_memory_keyboard(
    search_id: str,
    group_index: int,
    memory_groups: list[
        tuple[str, list[ProductCandidate]]
    ],
) -> InlineKeyboardMarkup:
    """Создаёт кнопки конфигураций памяти."""

    builder = InlineKeyboardBuilder()

    for memory_index, (label, _) in enumerate(
        memory_groups
    ):
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=(
                    f"olm:{search_id}:{group_index}:"
                    f"{memory_index}"
                ),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="⬅️ К моделям",
            callback_data=(
                f"olp:{search_id}:"
                f"{group_index // PRODUCT_PAGE_SIZE}"
            ),
        )
    )

    return builder.as_markup()


async def show_color_selection(
    message: Message,
    group: ProductVariantGroup,
    products: list[ProductCandidate],
    back_callback: str,
    any_callback: str | None = None,
    original_query: str | None = None,
    user_id: int | None = None,
    memory_selected: bool = True,
) -> None:
    """Shows color choices and skips memory wording when memory is not selectable."""

    colored_products = [
        product
        for product in products
        if requested_color_key(product.title) is not None
    ]
    selectable_products = colored_products or products

    choices: dict[tuple[str, str], ProductCandidate] = {}
    for product in selectable_products:
        color_key = requested_color_key(product.title) or "unknown"
        memory = extract_memory(product.title) or "Без выбора памяти"
        choice_memory = memory if memory_selected else ""
        choices.setdefault((color_key, choice_memory), product)

    if len(choices) == 1:
        only_product = next(iter(choices.values()))
        if requested_color_key(only_product.title) is None:
            await load_product_comparison(
                message=message,
                product_key=only_product.key,
                original_query=original_query,
                user_id=user_id,
            )
            return

    color_counts = Counter(
        color_key for color_key, _ in choices
    )
    builder = InlineKeyboardBuilder()
    if any_callback is not None:
        builder.row(
            InlineKeyboardButton(
                text="🎨 Любой — найти дешевле",
                callback_data=any_callback,
            )
        )
    sorted_choices = sorted(
        choices.items(),
        key=lambda item: (
            (selected_color_label(item[1].title) or "").casefold(),
            item[0][1],
            item[1].title.casefold(),
        ),
    )

    for (color_key, memory), product in sorted_choices:
        label = selected_color_label(product.title) or "Цвет не указан"
        if memory_selected and color_counts[color_key] > 1:
            label = f"{label} · {memory}"

        builder.row(
            InlineKeyboardButton(
                text=(
                    label
                    if len(label) <= 58
                    else label[:55] + "..."
                ),
                callback_data=f"ol:{product.key}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=back_callback,
        )
    )

    if any_callback is None:
        prompt = "Выбери цвет:"
    elif memory_selected:
        prompt = (
            "Выбери цвет или нажми «Любой», чтобы найти "
            "самую низкую цену среди всех цветов выбранной памяти:"
        )
    else:
        prompt = (
            "Выбери цвет или нажми «Любой», чтобы найти "
            "самую низкую цену среди всех цветов:"
        )

    await message.edit_text(
        f"🏷️ {group.title}\n\n{prompt}",
        reply_markup=builder.as_markup(),
    )

def store_product_search(
    products: list[ProductCandidate],
    parent: tuple[str, int] | None = None,
    query: str = "",
    owner_chat_id: int | None = None,
    owner_user_id: int | None = None,
) -> str:
    """Сохраняет результаты для пагинации."""

    search_id = secrets.token_urlsafe(6)
    product_searches[search_id] = products
    product_searches.move_to_end(search_id)
    product_session_registry.register(
        search_id,
        query=query,
        owner_chat_id=owner_chat_id,
        owner_user_id=owner_user_id,
    )
    for product in products:
        selection_query_registry.remember(
            chat_id=owner_chat_id,
            user_id=owner_user_id,
            product_key=product.key,
            query=query,
        )

    if parent is not None:
        product_search_parents[search_id] = parent

    while len(product_searches) > MAX_SEARCH_SESSIONS:
        expired_search_id, _ = product_searches.popitem(
            last=False
        )
        product_search_parents.pop(expired_search_id, None)
        product_session_registry.remove(expired_search_id)

    return search_id


def store_category_search(
    query: str,
    categories: list[ProductCategory],
    owner_chat_id: int | None = None,
    owner_user_id: int | None = None,
) -> str:
    """Сохраняет категории широкого запроса."""

    search_id = secrets.token_urlsafe(6)
    category_searches[search_id] = CategorySearchSession(
        query=query,
        categories=categories,
    )
    category_searches.move_to_end(search_id)
    category_session_registry.register(
        search_id,
        query=query,
        owner_chat_id=owner_chat_id,
        owner_user_id=owner_user_id,
    )

    while len(category_searches) > MAX_SEARCH_SESSIONS:
        expired_search_id, _ = category_searches.popitem(last=False)
        category_session_registry.remove(expired_search_id)

    return search_id


def build_category_keyboard(
    categories: list[ProductCategory],
    search_id: str,
    page: int,
) -> InlineKeyboardMarkup:
    """Создаёт страницу выбора категории."""

    builder = InlineKeyboardBuilder()
    start = page * CATEGORY_PAGE_SIZE
    end = start + CATEGORY_PAGE_SIZE

    for category_index, category in enumerate(
        categories[start:end],
        start=start,
    ):
        builder.row(
            InlineKeyboardButton(
                text=category.title,
                callback_data=(
                    f"olc:{search_id}:{category_index}"
                ),
            )
        )

    navigation: list[InlineKeyboardButton] = []

    if page > 0:
        navigation.extend(
            [
                InlineKeyboardButton(
                    text="⏮ В начало",
                    callback_data=f"olcp:{search_id}:0",
                ),
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=(
                        f"olcp:{search_id}:{page - 1}"
                    ),
                ),
            ]
        )

    if end < len(categories):
        navigation.append(
            InlineKeyboardButton(
                text="Далее ➡️",
                callback_data=f"olcp:{search_id}:{page + 1}",
            )
        )

    if navigation:
        builder.row(*navigation)

    return builder.as_markup()


def build_category_back_keyboard(
    search_id: str,
    page: int,
) -> InlineKeyboardMarkup:
    """Создаёт кнопку возврата к категориям."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ К категориям",
        callback_data=f"olcp:{search_id}:{page}",
    )
    return builder.as_markup()


def format_category_page_text(
    query: str,
    total: int,
    page: int,
) -> str:
    """Объясняет промежуточный выбор категории."""

    total_pages = max(
        1,
        (total + CATEGORY_PAGE_SIZE - 1)
        // CATEGORY_PAGE_SIZE,
    )

    return (
        f"Запрос «{query}» относится к нескольким "
        "категориям.\n"
        f"Страница {page + 1} из {total_pages}.\n\n"
        "Сначала выбери тип товара:"
    )


def format_product_page_text(
    total: int,
    page: int,
) -> str:
    """Показывает номер страницы модификаций."""

    total_pages = max(
        1,
        (total + PRODUCT_PAGE_SIZE - 1)
        // PRODUCT_PAGE_SIZE,
    )

    return (
        f"Нашёл вариантов: {total}.\n"
        f"Страница {page + 1} из {total_pages}.\n\n"
        "Выбери точную модель:"
    )


async def show_offers(
    message: Message,
    offers: list[ProductOffer],
) -> None:
    """Показывает предложения продавцов."""

    if not offers:
        await message.edit_text(
            "Доступных предложений не найдено."
        )
        return

    response_text = format_search_result(
        offers
    )

    await message.edit_text(
        response_text,
        disable_web_page_preview=True,
    )


def format_search_result(
    offers: list[ProductOffer],
) -> str:
    """Формирует итоговое сообщение."""

    product_title = display_product_title(
        offers[0].title
    )

    lines = [
        f"🏷️ {product_title}",
        "",
        "Найденные предложения:",
        "",
    ]

    for position, offer in enumerate(
        offers,
        start=1,
    ):
        lines.append(
            f"{position}. 🏪 "
            f"{offer.seller or offer.source}"
        )

        lines.append(
            f"💰 {offer.price:.2f} "
            f"{offer.currency}"
        )

        if offer.availability_text:
            lines.append(
                f"📦 {offer.availability_text}"
            )

        if offer.delivery_text:
            lines.append(
                "🚚 Доставка: "
                f"{offer.delivery_text}"
            )

        lines.append("")

    lines.extend(
        [
            "🔗 Все предложения:",
            offers[0].url,
            "",
            (
                "⚠️ Перед покупкой проверь "
                "цену и наличие у продавца."
            ),
        ]
    )

    return "\n".join(lines)

async def show_comparison(
    message: Message,
    offers: list[ProductOffer],
    source_statuses: (
        list[SourceSearchStatus] | None
    ) = None,
    product_key: str | None = None,
    product_title: str | None = None,
    grouped: bool = False,
) -> None:
    """Показывает сравнение площадок."""

    if not offers:
        await message.edit_text(
            "Доступных предложений не найдено."
        )
        return

    lines = ["🏆 Сравнение цен"]

    if product_title:
        lines.append(
            f"🏷️ {display_product_title(product_title)}"
        )

    lines.extend(
        [
            f"Найдено предложений: {len(offers)}",
            "",
        ]
    )

    for position, offer in enumerate(
        offers,
        start=1,
    ):
        medal = ""

        if position == 1:
            medal = "🥇 "
        elif position == 2:
            medal = "🥈 "
        elif position == 3:
            medal = "🥉 "

        lines.append(
            f"{medal}{position}. "
            f"{offer.source}"
        )

        if offer.seller:
            lines.append(
                f"🏪 {offer.seller}"
            )

        if not grouped:
            lines.append(
                f"🏷️ {display_product_title(offer.title)}"
            )

        lines.append(
            f"💰 {offer.price:.2f} "
            f"{offer.currency}"
        )

        if offer.availability_text:
            lines.append(
                f"📦 {offer.availability_text}"
            )

        if offer.delivery_text:
            lines.append(
                "🚚 Доставка: "
                f"{offer.delivery_text}"
            )

        lines.append(
            f"🔗 {offer.url}"
        )

        lines.append("")

    cheapest_offer = offers[0]

    if source_statuses:
        lines.extend(
            [
                "Проверенные источники:",
                *[
                    format_source_status(status)
                    for status in source_statuses
                ],
                "",
            ]
        )

    lines.extend(
        [
            "Самая низкая заявленная цена:",
            (
                f"✅ {cheapest_offer.price:.2f} "
                f"{cheapest_offer.currency} — "
                f"{cheapest_offer.seller or cheapest_offer.source}"
            ),
            "",
            (
                "ℹ️ Предложения объединены в одну карточку "
                "по модели и варианту товара."
                if grouped
                else (
                    "⚠️ Убедись, что ссылки ведут "
                    "на одинаковую модификацию товара."
                )
            ),
        ]
    )

    await message.edit_text(
        "\n".join(lines),
        disable_web_page_preview=True,
        reply_markup=(
            build_price_tracking_keyboard(product_key)
            if product_key
            else None
        ),
    )


def build_price_tracking_keyboard(
    product_key: str,
) -> InlineKeyboardMarkup:
    """Добавляет историю цены и подписку на снижение."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📉 История цены",
                    callback_data=f"price_history:{product_key}",
                ),
                InlineKeyboardButton(
                    text="🔔 Следить за ценой",
                    callback_data=f"price_alert:{product_key}",
                ),
            ]
        ]
    )


async def check_price_alerts(bot: Bot) -> None:
    """Один раз проверяет все активные подписки."""

    repository = get_price_history_repository()
    alerts = await asyncio.to_thread(repository.active_alerts)
    comparisons: dict[str, ComparisonResult | None] = {}

    for alert in alerts:
        if alert.product_key not in comparisons:
            try:
                comparison = (
                    await comparison_coordinator.run(
                        (alert.product_key, alert.query),
                        lambda: price_service.search_all_sources_by_onliner_key(
                            alert.product_key,
                            original_query=alert.query,
                        ),
                    )
                )
            except Exception:
                logger.exception(
                    "Price alert check failed: product=%s",
                    alert.product_key,
                )
                comparisons[alert.product_key] = None
            else:
                comparisons[alert.product_key] = comparison
                await asyncio.to_thread(
                    repository.record_offers,
                    alert.product_key,
                    (
                        comparison.master_product_title
                        or comparison.product_title
                        or alert.title
                    ),
                    comparison.offers,
                )

        comparison = comparisons[alert.product_key]

        if comparison is None:
            continue

        if not comparison.offers:
            await asyncio.to_thread(repository.mark_checked, alert)
            continue

        cheapest = comparison.offers[0]
        current_price = float(cheapest.price)

        if current_price < alert.last_notified_price:
            await bot.send_message(
                chat_id=alert.chat_id,
                text=(
                    "🔔 Цена снизилась\n\n"
                    f"🏷️ {display_product_title(alert.title)}\n"
                    f"💰 Было: {alert.last_notified_price:.2f} "
                    f"{alert.currency}\n"
                    f"✅ Стало: {current_price:.2f} "
                    f"{cheapest.currency} — "
                    f"{cheapest.seller or cheapest.source}\n"
                    f"🔗 {cheapest.url}"
                ),
                disable_web_page_preview=True,
            )
            await asyncio.to_thread(
                repository.mark_checked,
                alert,
                current_price,
            )
        else:
            await asyncio.to_thread(repository.mark_checked, alert)


async def run_price_alert_loop(
    bot: Bot,
    interval_seconds: int,
) -> None:
    """Периодически проверяет снижение цен до остановки бота."""

    while True:
        await asyncio.sleep(interval_seconds)
        await check_price_alerts(bot)


def format_source_status(
    status: SourceSearchStatus,
) -> str:
    """Объясняет результат проверки источника."""

    if status.state == "found":
        return (
            f"✅ {status.source} — "
            "предложение найдено"
        )

    if status.state == "filtered":
        return (
            f"⚠️ {status.source} — варианты найдены, "
            "но не совпали с выбранной моделью"
        )

    if status.state == "unavailable":
        return (
            f"❌ {status.source} — "
            "временно недоступен"
        )

    return (
        f"➖ {status.source} — "
        "точная модель не найдена"
    )


def message_chat_id(message: Message) -> int | None:
    """Безопасно получает идентификатор Telegram-чата."""

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    return chat_id if isinstance(chat_id, int) else None



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



def store_comparison_diagnostics(
    chat_id: int,
    comparison: ComparisonResult,
    user_id: int | None = None,
) -> None:
    """Сохраняет последний отчёт отдельно для каждого чата."""

    key = (chat_id, user_id)
    comparison_diagnostics[key] = comparison
    comparison_diagnostics.move_to_end(key)

    while (
        len(comparison_diagnostics)
        > MAX_DIAGNOSTIC_SESSIONS
    ):
        comparison_diagnostics.popitem(last=False)


def format_comparison_diagnostics(
    comparison: ComparisonResult,
) -> str:
    """Формирует компактный технический отчёт поиска."""

    state_labels = {
        "found": ("✅", "найдено"),
        "filtered": ("⚠️", "варианты отфильтрованы"),
        "not_found": ("➖", "не найдено"),
        "unavailable": ("❌", "недоступен"),
    }
    reason_labels = {
        "accessory": "аксессуар",
        "brand": "производитель",
        "bundle": "комплектация",
        "color": "цвет",
        "color_unknown": "цвет не указан",
        "configuration": "комплектация устройства",
        "condition": "состояние товара",
        "memory": "память",
        "model_code": "артикул",
        "model_number": "номер модели",
        "sim": "SIM-конфигурация",
        "version": "версия модели",
        "year": "год модели",
    }
    product_title = (
        comparison.master_product_title
        or comparison.product_title
    )

    if not product_title and comparison.offers:
        product_title = comparison.offers[0].title

    lines = [
        "🧪 Диагностика последнего сравнения",
        f"🏷️ {display_product_title(product_title) or 'Не определён'}",
    ]

    if comparison.catalog_presentation:
        lines.append(
            "🧩 Мастер-карточка: "
            f"{comparison.master_product_key or 'без ключа'}"
        )

    if comparison.query:
        lines.append(f"🔎 Запрос: {comparison.query}")

    if comparison.completed_at:
        lines.append(f"🕒 Завершено: {comparison.completed_at}")

    lines.extend(
        [
            (
                "⏱ Общее время: "
                f"{comparison.duration_seconds:.2f} с"
            ),
            f"🏷 Предложений в результате: {len(comparison.offers)}",
            "",
            "Источники:",
        ]
    )

    for status in comparison.source_statuses:
        icon, state_label = state_labels.get(
            status.state,
            ("❔", status.state),
        )
        lines.extend(
            [
                (
                    f"{icon} {status.source} — {state_label}; "
                    f"{status.duration_seconds:.2f} с"
                ),
                (
                    "   Проверено: "
                    f"{status.checked_candidates}; "
                    f"совпало: {status.matched_offers}"
                ),
            ]
        )

    rejected_reasons = Counter(
        decision.reason
        for decision in comparison.match_decisions
        if not decision.accepted
    )
    lines.extend(["", "Причины фильтрации:"])

    if rejected_reasons:
        lines.extend(
            f"• {reason_labels.get(reason, reason)}: {count}"
            for reason, count in sorted(rejected_reasons.items())
        )
    else:
        lines.append("• Отфильтрованных вариантов нет")

    return "\n".join(lines)


def build_five_element_keyboard(
    products: list[ProductCandidate],
) -> InlineKeyboardMarkup:
    """Создаёт кнопки товаров 5 элемента."""

    builder = InlineKeyboardBuilder()

    for product in products:
        button_text = product.title

        if len(button_text) > 58:
            button_text = (
                button_text[:55] + "..."
            )

        builder.button(
            text=button_text,
            callback_data=(
                f"fe:{product.key}"
            ),
        )

    builder.adjust(1)

    return builder.as_markup()
