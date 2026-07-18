import asyncio
import logging
import os
import secrets
from collections import Counter, OrderedDict
from dataclasses import dataclass
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
from app.services.price_service import PriceService
from app.services.price_history import PriceHistoryRepository
from app.services.product_variants import (
    ProductVariantGroup,
    display_color,
    display_product_title,
    group_by_memory,
    group_product_variants,
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
MAX_SEARCH_SESSIONS = 100
MAX_DIAGNOSTIC_SESSIONS = 1_000
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
    int,
    ComparisonResult,
] = OrderedDict()
price_history_repository: PriceHistoryRepository | None = None


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

    chat_id = message_chat_id(message)
    comparison = (
        comparison_diagnostics.get(chat_id)
        if chat_id is not None
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
    product_key = (callback.data or "").removeprefix(
        "price_alert:"
    )
    comparison = (
        comparison_diagnostics.get(chat_id)
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
        comparison.product_title or cheapest.title,
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

    await load_product_comparison(
        message=callback.message,
        product_key=product_key,
    )


async def load_product_comparison(
    message: Message,
    product_key: str,
) -> None:
    """Загружает сравнение выбранной модификации."""

    await message.edit_text(
        "🔎 Сравниваю цены Onliner, 21vek, "
        "5 элемента и Shop.by..."
    )

    try:
        comparison = (
            await price_service
            .search_all_sources_by_onliner_key(
                product_key
            )
        )
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
        logger.exception(
            "Unexpected product selection error"
        )

        await message.edit_text(
            "Произошла непредвиденная ошибка."
        )
        return

    chat_id = message_chat_id(message)

    if chat_id is not None:
        store_comparison_diagnostics(
            chat_id=chat_id,
            comparison=comparison,
        )

    await asyncio.to_thread(
        get_price_history_repository().record_offers,
        product_key,
        comparison.product_title,
        comparison.offers,
    )

    await show_comparison(
        message=message,
        offers=comparison.offers,
        source_statuses=(
            comparison.source_statuses
        ),
        product_key=product_key,
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
    products = product_searches.get(search_id)

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

    groups = group_product_variants(products)
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
    session = category_searches.get(search_id)

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
    session = category_searches.get(category_search_id)

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
        products = await price_service.find_onliner_products(
            query=session.query,
            category=category.key,
        )
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
    )
    groups = group_product_variants(products)

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
    """Показывает память выбранной модели."""

    await callback.answer()

    if callback.message is None:
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 3:
        return

    _, search_id, raw_group_index = parts
    products = product_searches.get(search_id)

    if products is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. "
            "Повтори запрос."
        )
        return

    try:
        group_index = int(raw_group_index)
        group = group_product_variants(products)[
            group_index
        ]
    except (ValueError, IndexError):
        return

    memory_groups = group_by_memory(group.products)

    if len(memory_groups) == 1:
        await show_color_selection(
            message=callback.message,
            group=group,
            products=memory_groups[0][1],
            back_callback=(
                f"olp:{search_id}:"
                f"{group_index // PRODUCT_PAGE_SIZE}"
            ),
        )
        return

    await callback.message.edit_text(
        f"📱 {group.title}\n\n"
        "Выбери объём памяти:",
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
    products = product_searches.get(search_id)

    if products is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. "
            "Повтори запрос."
        )
        return

    try:
        group_index = int(raw_group_index)
        memory_index = int(raw_memory_index)
        group = group_product_variants(products)[
            group_index
        ]
        memory_products = group_by_memory(
            group.products
        )[memory_index][1]
    except (ValueError, IndexError):
        return

    await show_color_selection(
        message=callback.message,
        group=group,
        products=memory_products,
        back_callback=(
            f"olg:{search_id}:{group_index}"
        ),
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

    query = command_parts[1].strip()

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

    query = (message.text or "").strip()

    if query.startswith("/"):
        await message.answer(
            "Неизвестная команда.\n"
            "Используй /help."
        )
        return

    if len(query) < 3:
        await message.answer(
            "Название слишком короткое.\n"
            "Укажи модель товара."
        )
        return

    status_message = await message.answer(
        "🔎 Ищу подходящие товары..."
    )

    try:
        categories: list[ProductCategory] = []

        if price_service.should_categorize_query(query):
            categories = (
                await price_service.find_onliner_categories(query)
            )

        if len(categories) > 1:
            category_search_id = store_category_search(
                query=query,
                categories=categories,
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

        products = (
            await price_service
            .find_onliner_products(
                query,
                category=(
                    categories[0].key
                    if len(categories) == 1
                    else None
                ),
            )
        )
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

    search_id = store_product_search(products)
    groups = group_product_variants(products)
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
    groups = group_product_variants(products)
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

        if len(group.products) == 1:
            callback_data = (
                f"ol:{group.products[0].key}"
            )
        else:
            callback_data = (
                f"olg:{search_id}:{group_index}"
            )

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
) -> None:
    """Показывает цвета или сразу открывает товар."""

    if len(products) == 1:
        await load_product_comparison(
            message=message,
            product_key=products[0].key,
        )
        return

    builder = InlineKeyboardBuilder()
    used_labels: set[str] = set()

    sorted_products = sorted(
        products,
        key=lambda product: (
            (
                display_color(product.title)
                or product.title
            ).casefold(),
            product.title.casefold(),
        ),
    )

    for product in sorted_products:
        label = display_color(product.title)

        if label is None:
            label = product.title

        normalized_label = label.casefold()

        if normalized_label in used_labels:
            continue

        used_labels.add(normalized_label)
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

    await message.edit_text(
        f"📱 {group.title}\n\n"
        "Выбери цвет или вариант:",
        reply_markup=builder.as_markup(),
    )


def store_product_search(
    products: list[ProductCandidate],
    parent: tuple[str, int] | None = None,
) -> str:
    """Сохраняет результаты для пагинации."""

    search_id = secrets.token_urlsafe(6)
    product_searches[search_id] = products
    product_searches.move_to_end(search_id)

    if parent is not None:
        product_search_parents[search_id] = parent

    while len(product_searches) > MAX_SEARCH_SESSIONS:
        expired_search_id, _ = product_searches.popitem(
            last=False
        )
        product_search_parents.pop(expired_search_id, None)

    return search_id


def store_category_search(
    query: str,
    categories: list[ProductCategory],
) -> str:
    """Сохраняет категории широкого запроса."""

    search_id = secrets.token_urlsafe(6)
    category_searches[search_id] = CategorySearchSession(
        query=query,
        categories=categories,
    )
    category_searches.move_to_end(search_id)

    while len(category_searches) > MAX_SEARCH_SESSIONS:
        category_searches.popitem(last=False)

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
        f"📱 {product_title}",
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

        if offer.updated_at:
            lines.append(
                "🕒 Обновлено: "
                f"{offer.updated_at}"
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
) -> None:
    """Показывает сравнение площадок."""

    if not offers:
        await message.edit_text(
            "Доступных предложений не найдено."
        )
        return

    lines = [
        "🏆 Сравнение цен",
        f"Найдено предложений: {len(offers)}",
        "",
    ]

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

        lines.append(
            f"📱 {display_product_title(offer.title)}"
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

        if offer.updated_at:
            lines.append(
                "🕒 Обновлено: "
                f"{offer.updated_at}"
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
                "⚠️ Убедись, что ссылки ведут "
                "на одинаковую модификацию товара."
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
                    await price_service.search_all_sources_by_onliner_key(
                        alert.product_key
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
                    comparison.product_title or alert.title,
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
                    f"📱 {display_product_title(alert.title)}\n"
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


def store_comparison_diagnostics(
    chat_id: int,
    comparison: ComparisonResult,
) -> None:
    """Сохраняет последний отчёт отдельно для каждого чата."""

    comparison_diagnostics[chat_id] = comparison
    comparison_diagnostics.move_to_end(chat_id)

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
        "configuration": "комплектация устройства",
        "condition": "состояние товара",
        "memory": "память",
        "model_code": "артикул",
        "model_number": "номер модели",
        "sim": "SIM-конфигурация",
        "version": "версия модели",
        "year": "год модели",
    }
    product_title = comparison.product_title

    if not product_title and comparison.offers:
        product_title = comparison.offers[0].title

    lines = [
        "🧪 Диагностика последнего сравнения",
        f"📱 {display_product_title(product_title) or 'Не определён'}",
    ]

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
