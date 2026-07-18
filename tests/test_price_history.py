import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from app.handlers import search
from app.models.offer import ProductOffer
from app.models.search_result import ComparisonResult
from app.services.price_history import PriceHistoryRepository


def offer(source: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        title="Apple iPhone 17 Pro 256GB Deep Blue",
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{source}",
        seller=source,
    )


class PriceHistoryRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.repository = PriceHistoryRepository(
            Path(self.temp_directory.name) / "prices.sqlite3"
        )
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_records_minimum_price_per_search(self) -> None:
        self.repository.record_offers(
            "iphone17pro256blue",
            "iPhone 17 Pro",
            [offer("Onliner", 3900), offer("21vek", 3600)],
            observed_at="2026-07-18T10:00:00+00:00",
        )
        self.repository.record_offers(
            "iphone17pro256blue",
            "iPhone 17 Pro",
            [offer("5 элемент", 3500)],
            observed_at="2026-07-18T12:00:00+00:00",
        )

        points = self.repository.history("iphone17pro256blue")

        self.assertEqual(
            [(point.price, point.source) for point in points],
            [(3500, "5 элемент"), (3600, "21vek")],
        )

    def test_toggles_and_updates_persistent_alert(self) -> None:
        enabled = self.repository.toggle_alert(
            100,
            "iphone17pro256blue",
            "iPhone 17 Pro",
            "iPhone 17 Pro 256GB",
            3600,
            "BYN",
        )
        alert = self.repository.active_alerts()[0]

        self.assertTrue(enabled)
        self.assertEqual(alert.last_notified_price, 3600)

        self.repository.mark_checked(alert, notified_price=3490)
        updated = self.repository.active_alerts()[0]
        self.assertEqual(updated.last_notified_price, 3490)

        disabled = self.repository.toggle_alert(
            100,
            "iphone17pro256blue",
            "iPhone 17 Pro",
            "iPhone 17 Pro 256GB",
            3490,
            "BYN",
        )
        self.assertFalse(disabled)
        self.assertEqual(self.repository.active_alerts(), [])

class PriceAlertCheckTest(unittest.IsolatedAsyncioTestCase):
    async def test_notifies_only_after_a_new_price_drop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = PriceHistoryRepository(
                Path(directory) / "prices.sqlite3"
            )
            repository.initialize()
            repository.toggle_alert(
                100,
                "iphone17pro256blue",
                "Apple iPhone 17 Pro 256GB Deep Blue",
                "iPhone 17 Pro 256GB",
                3600,
                "BYN",
            )
            comparison = ComparisonResult(
                offers=[offer("Shop.by", 3490)],
                source_statuses=[],
                match_decisions=[],
                product_title="Apple iPhone 17 Pro 256GB Deep Blue",
                product_key="iphone17pro256blue",
            )
            previous_repository = search.price_history_repository
            previous_search = (
                search.price_service.search_all_sources_by_onliner_key
            )
            search.price_history_repository = repository
            search.price_service.search_all_sources_by_onliner_key = (
                AsyncMock(return_value=comparison)
            )
            bot = AsyncMock()

            try:
                await search.check_price_alerts(bot)
                await search.check_price_alerts(bot)
            finally:
                search.price_history_repository = previous_repository
                search.price_service.search_all_sources_by_onliner_key = (
                    previous_search
                )

            bot.send_message.assert_awaited_once()
            alert = repository.active_alerts()[0]
            self.assertEqual(alert.last_notified_price, 3490)


if __name__ == "__main__":
    unittest.main()
