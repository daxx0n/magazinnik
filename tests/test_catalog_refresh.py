import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.handlers.catalog import (
    format_catalog_refresh_report,
    format_catalog_refresh_status,
)
from app.models.catalog import (
    ExternalCatalogItem,
    MasterCatalogProduct,
    ProductIdentity,
)
from app.services.catalog_refresh import (
    CatalogRefreshConfig,
    CatalogRefreshService,
)
from app.services.catalog_service import CatalogService
from app.services.master_catalog import MasterCatalog


class FakeCatalogPriceService:
    def __init__(
        self,
        catalog_service: CatalogService,
        freshness: timedelta,
        failures: set[str] | None = None,
        unchanged: set[str] | None = None,
    ) -> None:
        self._catalog_service = catalog_service
        self._catalog_freshness = freshness
        self.failures = failures or set()
        self.unchanged = unchanged or set()
        self.calls: list[str] = []

    async def search_all_sources_by_onliner_key(self, key: str):
        self.calls.append(key)
        product_key = key.removeprefix("catalog:")
        if product_key in self.failures:
            raise RuntimeError("source unavailable")

        product = next(
            item
            for item in self._catalog_service.catalog.products
            if item.key == product_key
        )
        if product_key not in self.unchanged:
            for offer in product.offers:
                offer.updated_at = datetime.now(timezone.utc)

        return SimpleNamespace(offers=[object()] * len(product.offers))


class CatalogRefreshTest(unittest.IsolatedAsyncioTestCase):
    now = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)

    @staticmethod
    def product(
        key: str,
        title: str,
        updated_at: datetime,
    ) -> MasterCatalogProduct:
        identity = ProductIdentity(
            brand="google",
            model=title.casefold(),
        )
        return MasterCatalogProduct(
            key=key,
            title=title,
            identity=identity,
            offers=[
                ExternalCatalogItem(
                    source="Onliner",
                    external_id=f"offer-{key}",
                    title=title,
                    url=f"https://example.com/{key}",
                    price=1000.0,
                    currency="BYN",
                    identity=identity,
                    updated_at=updated_at,
                )
            ],
        )

    def build_service(
        self,
        products: list[MasterCatalogProduct],
        *,
        config: CatalogRefreshConfig | None = None,
        failures: set[str] | None = None,
        unchanged: set[str] | None = None,
    ) -> tuple[CatalogRefreshService, FakeCatalogPriceService]:
        catalog = MasterCatalog()
        catalog.restore(products)
        catalog_service = CatalogService(
            catalog=catalog,
            restore_on_start=False,
        )
        price_service = FakeCatalogPriceService(
            catalog_service=catalog_service,
            freshness=timedelta(hours=24),
            failures=failures,
            unchanged=unchanged,
        )
        refresh_service = CatalogRefreshService(
            price_service=price_service,  # type: ignore[arg-type]
            config=config
            or CatalogRefreshConfig(
                enabled=True,
                interval_seconds=3600,
                initial_delay_seconds=0,
                batch_size=10,
                concurrency=1,
            ),
        )
        return refresh_service, price_service

    def test_selects_only_stale_products_oldest_first(self) -> None:
        service, _ = self.build_service(
            [
                self.product(
                    "product-fresh",
                    "Google Pixel 9",
                    self.now - timedelta(hours=2),
                ),
                self.product(
                    "product-old",
                    "Google Pixel 7",
                    self.now - timedelta(hours=72),
                ),
                self.product(
                    "product-stale",
                    "Google Pixel 8",
                    self.now - timedelta(hours=30),
                ),
            ]
        )

        self.assertEqual(
            [item.key for item in service.stale_products(self.now)],
            ["product-old", "product-stale"],
        )

    async def test_refreshes_bounded_batch_and_reports_failures(self) -> None:
        config = CatalogRefreshConfig(
            enabled=True,
            interval_seconds=3600,
            initial_delay_seconds=0,
            batch_size=2,
            concurrency=1,
        )
        service, price_service = self.build_service(
            [
                self.product(
                    "product-1",
                    "Google Pixel 7",
                    self.now - timedelta(hours=72),
                ),
                self.product(
                    "product-2",
                    "Google Pixel 8",
                    self.now - timedelta(hours=60),
                ),
                self.product(
                    "product-3",
                    "Google Pixel 9",
                    self.now - timedelta(hours=48),
                ),
            ],
            config=config,
            failures={"product-2"},
        )

        with patch(
            "app.services.catalog_refresh.datetime"
        ) as datetime_mock:
            datetime_mock.now.return_value = self.now
            report = await service.refresh_once()

        self.assertEqual(
            price_service.calls,
            ["catalog:product-1", "catalog:product-2"],
        )
        self.assertEqual(report.selected_products, 2)
        self.assertEqual(report.refreshed_products, 1)
        self.assertEqual(report.failed_products, 1)
        self.assertEqual(report.unchanged_products, 0)
        self.assertEqual(report.items[1].state, "failed")
        self.assertIn("RuntimeError", report.items[1].error)

    async def test_reports_successful_call_without_timestamp_change(self) -> None:
        service, _ = self.build_service(
            [
                self.product(
                    "product-1",
                    "Google Pixel 8",
                    self.now - timedelta(hours=48),
                )
            ],
            unchanged={"product-1"},
        )

        with patch(
            "app.services.catalog_refresh.datetime"
        ) as datetime_mock:
            datetime_mock.now.return_value = self.now
            report = await service.refresh_once()

        self.assertEqual(report.refreshed_products, 0)
        self.assertEqual(report.unchanged_products, 1)
        self.assertEqual(report.failed_products, 0)

    async def test_skips_overlapping_cycle(self) -> None:
        service, _ = self.build_service([])
        await service._lock.acquire()
        try:
            report = await service.refresh_once()
        finally:
            service._lock.release()

        self.assertEqual(report.status, "overlap_skipped")
        self.assertEqual(report.selected_products, 0)

    def test_environment_config_is_clamped(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CATALOG_REFRESH_ENABLED": "true",
                "CATALOG_REFRESH_INTERVAL_SECONDS": "10",
                "CATALOG_REFRESH_INITIAL_DELAY_SECONDS": "99999",
                "CATALOG_REFRESH_BATCH_SIZE": "999",
                "CATALOG_REFRESH_CONCURRENCY": "8",
            },
            clear=False,
        ):
            config = CatalogRefreshConfig.from_environment()

        self.assertTrue(config.enabled)
        self.assertEqual(config.interval_seconds, 300.0)
        self.assertEqual(config.initial_delay_seconds, 3600.0)
        self.assertEqual(config.batch_size, 100)
        self.assertEqual(config.concurrency, 3)

    def test_formats_refresh_status_and_report(self) -> None:
        service, _ = self.build_service(
            [
                self.product(
                    "product-1",
                    "Google Pixel 8",
                    self.now - timedelta(hours=48),
                )
            ]
        )
        status = format_catalog_refresh_status(service)

        self.assertIn("Фоновый режим: включён", status)
        self.assertIn("Размер пакета: 10", status)
        self.assertIn("Последний запуск: ещё не выполнялся", status)

        async def run_and_format() -> str:
            with patch(
                "app.services.catalog_refresh.datetime"
            ) as datetime_mock:
                datetime_mock.now.return_value = self.now
                report = await service.refresh_once()
            return format_catalog_refresh_report(report)

        text = asyncio.run(run_and_format())
        self.assertIn("Цикл обновления завершён", text)
        self.assertIn("Обновлено: 1", text)


if __name__ == "__main__":
    unittest.main()
