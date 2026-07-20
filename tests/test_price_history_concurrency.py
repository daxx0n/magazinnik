import asyncio
import tempfile
import unittest
from pathlib import Path

from app.models.offer import ProductOffer
from app.services.price_history import PriceHistoryRepository


def offer(index: int) -> ProductOffer:
    return ProductOffer(
        source=f"source-{index % 6}",
        title="Google Pixel 8 8GB/128GB (Obsidian)",
        price=1_000.0 + index,
        currency="BYN",
        available=True,
        url=f"https://example.com/{index}",
        seller=f"seller-{index}",
    )


class PriceHistoryConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = PriceHistoryRepository(
            Path(self.temp_dir.name) / "prices.sqlite3"
        )
        self.repository.initialize()

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_fifty_parallel_history_writes_do_not_lock_database(self) -> None:
        await asyncio.gather(
            *(
                asyncio.to_thread(
                    self.repository.record_offers,
                    "pixel8",
                    "Google Pixel 8",
                    [offer(index)],
                    f"2026-07-20T00:00:{index:02d}+00:00",
                )
                for index in range(50)
            )
        )

        points = self.repository.history("pixel8", limit=100)
        self.assertEqual(len(points), 50)
        self.assertEqual(min(point.price for point in points), 1_000.0)

    async def test_fifty_users_can_toggle_distinct_alerts_concurrently(self) -> None:
        results = await asyncio.gather(
            *(
                asyncio.to_thread(
                    self.repository.toggle_alert,
                    index,
                    "pixel8",
                    "Google Pixel 8",
                    "Pixel",
                    2_000.0,
                    "BYN",
                )
                for index in range(50)
            )
        )

        self.assertEqual(results, [True] * 50)
        self.assertEqual(len(self.repository.active_alerts()), 50)

    def test_invalid_prices_are_not_persisted(self) -> None:
        invalid = ProductOffer(
            source="source",
            title="Broken price",
            price=float("nan"),
            currency="BYN",
            available=True,
            url="https://example.com/broken",
        )
        self.repository.record_offers("broken", "Broken", [invalid])
        self.assertEqual(self.repository.history("broken"), [])
        with self.assertRaises(ValueError):
            self.repository.toggle_alert(
                1,
                "broken",
                "Broken",
                "Broken",
                float("inf"),
                "BYN",
            )

    def test_history_limit_is_clamped(self) -> None:
        self.repository.record_offers(
            "pixel8",
            "Google Pixel 8",
            [offer(1)],
            "2026-07-20T00:00:01+00:00",
        )
        self.assertEqual(len(self.repository.history("pixel8", limit=-100)), 1)


if __name__ == "__main__":
    unittest.main()
