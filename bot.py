import asyncio
import contextlib
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
    search.initialize_price_history(config.price_database_path)
    alert_task = asyncio.create_task(
        search.run_price_alert_loop(
            bot,
            config.price_alert_interval_seconds,
        )
    )

    try:
        print(
            "Бот запущен. "
            "Для остановки нажми Control + C."
        )

        await dispatcher.start_polling(bot)
    finally:
        alert_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await alert_task

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
