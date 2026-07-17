import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import (
    InlineKeyboardBuilder,
)

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.price_service import PriceService
from app.sources import (
    InvalidProductUrlError,
    ProductNotFoundError,
    SourceUnavailableError,
)


router = Router(name="search")

price_service = PriceService()

logger = logging.getLogger(__name__)


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

    callback_data = callback.data or ""
    product_key = callback_data.removeprefix(
        "ol:"
    )

    await callback.message.edit_text(
        "🔎 Получаю предложения продавцов..."
    )

    try:
        offers = (
            await price_service.search_onliner_key(
                product_key
            )
        )
    except ProductNotFoundError as error:
        await callback.message.edit_text(
            f"Предложения не найдены.\n\n{error}"
        )
        return
    except SourceUnavailableError as error:
        logger.warning(
            "Onliner unavailable: %s",
            error,
        )

        await callback.message.edit_text(
            "Onliner временно недоступен.\n"
            "Попробуй повторить запрос."
        )
        return
    except Exception:
        logger.exception(
            "Unexpected product selection error"
        )

        await callback.message.edit_text(
            "Произошла непредвиденная ошибка."
        )
        return

    await show_offers(
        message=callback.message,
        offers=offers,
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
            "5element index unavailable: %s",
            error,
        )

        await status_message.edit_text(
            "Поиск 5 элемента недоступен.\n\n"
            f"{error}"
        )
        return

    except Exception:
        logger.exception(
            "Unexpected 5element index error"
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
        products = (
            await price_service
            .find_onliner_products(query)
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

    keyboard = build_product_keyboard(
        products
    )

    await status_message.edit_text(
        "Нашёл несколько вариантов.\n\n"
        "Выбери точную модель:",
        reply_markup=keyboard,
    )


def build_product_keyboard(
    products: list[ProductCandidate],
) -> InlineKeyboardMarkup:
    """Создаёт кнопки выбора товара."""

    builder = InlineKeyboardBuilder()

    for product in products:
        button_text = product.title

        if len(button_text) > 58:
            button_text = (
                button_text[:55] + "..."
            )

        builder.button(
            text=button_text,
            callback_data=f"ol:{product.key}",
        )

    builder.adjust(1)

    return builder.as_markup()


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

    product_title = offers[0].title

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
) -> None:
    """Показывает сравнение площадок."""

    if not offers:
        await message.edit_text(
            "Доступных предложений не найдено."
        )
        return

    lines = [
        "🏆 Сравнение цен",
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
            f"📱 {offer.title}"
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
    )
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