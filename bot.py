import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.handlers import common, search


async def main() -> None:
    """Точка запуска Telegram-бота."""

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )

    config = load_config()

    bot = Bot(token=config.bot_token)
    dispatcher = Dispatcher()

    dispatcher.include_router(common.router)
    dispatcher.include_router(search.router)

    try:
        print(
            "Бот запущен. "
            "Для остановки нажми Control + C."
        )

        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
