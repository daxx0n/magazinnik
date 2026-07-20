import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.handlers import catalog, common, search
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.catalog_refresh import CatalogRefreshService


search.price_service = CatalogFirstPriceService(
    catalog_service=search.price_service._catalog_service,
)
catalog_refresh_service = CatalogRefreshService(search.price_service)
catalog.initialize_catalog_refresh(catalog_refresh_service)


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
    dispatcher.include_router(catalog.router)
    dispatcher.include_router(search.router)
    search.initialize_price_history(config.price_database_path)

    background_tasks = [
        asyncio.create_task(
            search.run_price_alert_loop(
                bot,
                config.price_alert_interval_seconds,
            ),
            name="price-alert-loop",
        )
    ]
    if catalog_refresh_service.enabled:
        background_tasks.append(
            asyncio.create_task(
                catalog_refresh_service.run_forever(),
                name="catalog-refresh-loop",
            )
        )

    try:
        print(
            "Бот запущен. "
            "Для остановки нажми Control + C."
        )

        await dispatcher.start_polling(bot)
    finally:
        for task in background_tasks:
            task.cancel()

        for task in background_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
