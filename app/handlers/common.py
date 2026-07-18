from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message


router = Router(name="common")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Обрабатывает команду /start."""

    await message.answer(
        "Привет! 👋\n\n"
        "Я помогу сравнить цены на товары "
        "в белорусских интернет-магазинах.\n\n"
        "Отправь название товара, например:\n"
        "iPhone 17 256GB\n\n"
        "После сравнения можно посмотреть историю цены "
        "и включить уведомление о снижении.\n\n"
        "Доступные команды:\n"
        "/help — инструкция\n"
        "/diagnostics — отчёт последнего поиска"
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Показывает инструкцию."""

    await message.answer(
        "Как пользоваться ботом:\n\n"
        "🔎 Сравнение цен в Onliner, "
        "21vek, 5 элементе, Shop.by и Электросиле:\n"
        "Просто отправь название товара.\n\n"
        "Под результатом доступны кнопки истории цены "
        "и уведомления о снижении.\n\n"
        "Диагностика последнего сравнения:\n"
        "/diagnostics\n\n"
        "Прямая ссылка Onliner:\n"
        "/onliner ССЫЛКА\n\n"
        "Прямая ссылка 21vek:\n"
        "/twentyone ССЫЛКА\n\n"
        "Прямая ссылка 5 элемента:\n"
        "/five ССЫЛКА\n\n"
        "🔎 Поиск в 5 элементе:\n"
        "/five_search НАЗВАНИЕ\n\n"
        "Сравнение Onliner и 5 элемента:\n"
        "/compare "
        "ССЫЛКА_ONLINER "
        "ССЫЛКА_5ELEMENT"
    )
