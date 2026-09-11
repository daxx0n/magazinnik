import asyncio
import contextlib
import logging
import os

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.handlers import catalog, catalog_feed, common, search
from app.services.catalog_feed_upload import CatalogFeedUploadManager
from app.services.unified_catalog import UnifiedCatalogPriceService
from app.services.catalog_refresh import CatalogRefreshService
from app.services.catalog_service import CatalogService
from app.services.sqlite_catalog_storage import SqliteCatalogStorage
from app.services.selection_presentation import (
    group_selection_model_variants,
    selection_color_key,
    selection_color_label,
)


search.price_service = UnifiedCatalogPriceService(
    catalog_service=CatalogService(
        storage=SqliteCatalogStorage(
            os.getenv("CATALOG_DATABASE_PATH", "data/unified_catalog.sqlite3")
        )
    ),
)
# UI uses exact marketing colors without changing the production matcher.
search.group_model_variants = group_selection_model_variants
search.requested_color_key = selection_color_key
search.selected_color_label = selection_color_label

catalog_refresh_service = CatalogRefreshService(search.price_service)
catalog.initialize_catalog_refresh(catalog_refresh_service)
catalog_feed.initialize_catalog_feed_upload(
    CatalogFeedUploadManager(search.price_service._catalog_service)
)


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
    dispatcher.include_router(catalog_feed.router)
    dispatcher.include_router(search.router)
    search.initialize_price_history(config.price_database_path)

    background_tasks = [
        asyncio.create_task(
            search.run_price_alert_loop(
                bot,
                config.price_alert_interval_seconds,
            ),
            name="price-alert-loop",
        ),
        asyncio.create_task(
            search.price_service.run_discovery_loop(),
            name="catalog-discovery-loop",
        ),
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

        await search.price_service.close()

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
