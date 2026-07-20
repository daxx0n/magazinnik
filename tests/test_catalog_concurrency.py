import asyncio
import tempfile
import unittest
from pathlib import Path

from app.models.offer import ProductOffer
from app.services.catalog_service import CatalogService
from app.services.sqlite_catalog_storage import SqliteCatalogStorage


def offer(index: int) -> ProductOffer:
    return ProductOffer(
        source=f"source-{index % 6}",
        title="Google Pixel 8 8GB/128GB (Obsidian)",
        price=2_000.0 + index,
        currency="BYN",
        available=True,
        url=f"https://example.com/pixel8/{index}",
        seller=f"seller-{index}",
    )


class CatalogConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_fifty_parallel_ingests_do_not_deadlock_or_lose_offers(self) -> None:
        service = CatalogService()

        reports = await asyncio.wait_for(
            asyncio.gather(
                *(
                    service.ingest_offers_with_report_async([offer(index)])
                    for index in range(50)
                )
            ),
            timeout=10,
        )

        self.assertEqual(len(reports), 50)
        products = service.search("Google Pixel 8")
        self.assertEqual(len(products), 1)
        self.assertEqual(len(products[0].offers), 50)
        self.assertEqual(service.metrics.batches, 50)

    async def test_sqlite_snapshot_remains_restorable_after_parallel_ingests(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.sqlite3"
            service = CatalogService(
                storage=SqliteCatalogStorage(path),
                restore_on_start=False,
            )

            await asyncio.wait_for(
                asyncio.gather(
                    *(
                        service.ingest_offers_with_report_async([offer(index)])
                        for index in range(30)
                    )
                ),
                timeout=15,
            )

            restored = CatalogService(
                storage=SqliteCatalogStorage(path),
                restore_on_start=True,
            )
            products = restored.search("Google Pixel 8")
            self.assertEqual(len(products), 1)
            self.assertEqual(len(products[0].offers), 30)

    async def test_async_ingest_keeps_event_loop_responsive(self) -> None:
        service = CatalogService()
        ticks = 0
        running = True

        async def ticker() -> None:
            nonlocal ticks
            while running:
                ticks += 1
                await asyncio.sleep(0)

        ticker_task = asyncio.create_task(ticker())
        try:
            await asyncio.gather(
                *(
                    service.ingest_offers_with_report_async([offer(index)])
                    for index in range(20)
                )
            )
        finally:
            running = False
            await ticker_task

        self.assertGreater(ticks, 1)


if __name__ == "__main__":
    unittest.main()
