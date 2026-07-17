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
        "Доступные команды:\n"
        "/help — инструкция"
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Показывает инструкцию."""

    await message.answer(
        "Как пользоваться ботом:\n\n"
        "🔎 Поиск Onliner:\n"
        "Просто отправь название товара.\n\n"
        "Прямая ссылка Onliner:\n"
        "/onliner ССЫЛКА\n\n"
        "Прямая ссылка 21vek:\n"
        "/twentyone ССЫЛКА\n\n"
        "Прямая ссылка 5 элемента:\n"
        "/five ССЫЛКА\n\n"
        "Сравнение Onliner и 5 элемента:\n"
        "/compare "
        "ССЫЛКА_ONLINER "
        "ССЫЛКА_5ELEMENT\n\n"
        "⚠️ Автоматический поиск "
        "5 элемента временно отключён."
    )