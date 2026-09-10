import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.handlers import search
from app.models.catalog import ExternalCatalogItem, ProductIdentity
from app.models.offer import ProductOffer
from app.models.search_result import ComparisonResult
from app.services.master_catalog import MasterCatalog
from app.services.price_history import PriceHistoryRepository
from app.services.search_load import SearchBusyError, SearchRequestCoordinator
from app.services.telegram_text import split_message


def offer(price=900, currency="BYN", **kwargs):
    return ProductOffer(source="fixture", title="Google Pixel 8 128GB Black",
                        price=price, currency=currency, available=True,
                        url="https://example.test/pixel8", **kwargs)


def comparison(offers):
    return ComparisonResult(offers=offers, source_statuses=[], match_decisions=[], product_key="pixel8")


class CatalogGenerationRegressionTest(unittest.TestCase):
    def test_different_model_numbers_never_merge(self):
        for brand, left, right in (
            ("Samsung", "Galaxy S24", "Galaxy S25"),
            ("Apple", "iPhone 15 Pro", "iPhone 16 Pro"),
            ("Bosch", "HBA534EB3", "HBA534EB4"),
            ("LG", "OLED55C4", "OLED65C4"),
            ("Google", "Pixel 8", "Pixel 9"),
        ):
            with self.subTest(brand=brand, left=left, right=right):
                catalog = MasterCatalog()
                keys = []
                for model in (left, right):
                    item = ExternalCatalogItem(
                        source="fixture", external_id=model, title=f"{brand} {model}",
                        url="https://example.test/product", price=1000, currency="BYN",
                        identity=ProductIdentity(brand=brand, model=model, memory="256GB", color="Black"),
                    )
                    keys.append(catalog.upsert(item).key)
                self.assertNotEqual(*keys)
                self.assertEqual(len(catalog.products), 2)


class ComparisonLengthRegressionTest(unittest.IsolatedAsyncioTestCase):
    def test_split_preserves_all_text_and_unicode_boundaries(self):
        for text in ("", "abc", "a" * 12000, "\n" * 5000, "🏪\n" * 6000, "Доставка " * 1000):
            with self.subTest(length=len(text)):
                chunks = split_message(text)
                self.assertEqual("".join(chunks), text)
                self.assertTrue(all(0 < len(chunk.encode("utf-16-le")) // 2 <= 4000 for chunk in chunks))

    async def test_all_offers_survive_telegram_message_limit(self):
        message = AsyncMock()
        rendered = []

        async def send(text, **kwargs):
            self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4096)
            rendered.append(text)

        message.edit_text.side_effect = send
        message.answer.side_effect = send
        offers = [replace(offer(), url=f"https://example.test/product/{index}",
                          seller="магазин " + "🏪" * 100,
                          delivery_text="Доставка " + "подробности " * 40)
                  for index in range(40)]
        await search.show_comparison(message, offers, product_key="pixel8")
        combined = "\n".join(rendered)
        for item in offers:
            self.assertIn(item.url, combined)
        self.assertIn("Самая низкая заявленная цена", combined)

    async def test_one_oversized_field_is_split_without_losing_text(self):
        message = AsyncMock()
        await search.show_comparison(message, [offer(delivery_text="🚚" * 5000)])
        calls = message.edit_text.call_args_list + message.answer.call_args_list
        for call in calls:
            self.assertLessEqual(len(call.args[0].encode("utf-16-le")) // 2, 4096)
        self.assertEqual("".join(call.args[0] for call in calls).count("🚚"), 5001)


class AlertResilienceRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repository = PriceHistoryRepository(Path(self.directory.name) / "prices.sqlite3")
        self.repository.initialize()
        for chat in (101, 102):
            self.repository.toggle_alert(chat, "pixel8", "Pixel 8", "Pixel 8", 1000, "BYN")
        self.enterContext(patch.object(search, "get_price_history_repository", return_value=self.repository))
        self.enterContext(patch.object(search, "comparison_coordinator", SearchRequestCoordinator()))
        self.service = Mock()
        self.service.search_all_sources_by_onliner_key = AsyncMock(return_value=comparison([offer()]))
        self.enterContext(patch.object(search, "price_service", self.service))
        self.enterContext(patch.object(search, "logger"))

    async def test_failed_recipient_does_not_block_other_subscribers(self):
        bot = AsyncMock()
        bot.send_message.side_effect = [RuntimeError("Telegram unavailable for chat"), None]
        await search.check_price_alerts(bot)
        self.assertEqual(bot.send_message.await_count, 2)
        prices = {alert.chat_id: alert.last_notified_price for alert in self.repository.active_alerts()}
        self.assertEqual(prices, {101: 1000, 102: 900})

    async def test_currency_change_is_not_a_price_drop(self):
        self.service.search_all_sources_by_onliner_key.return_value = comparison([offer(300, "USD")])
        bot = AsyncMock()
        await search.check_price_alerts(bot)
        bot.send_message.assert_not_awaited()
        self.assertTrue(all(alert.last_notified_price == 1000 for alert in self.repository.active_alerts()))

    async def test_unavailable_and_nonfinite_prices_are_ignored(self):
        self.service.search_all_sources_by_onliner_key.return_value = comparison([
            replace(offer(100), available=False), offer(float("nan")),
            offer(float("inf")), offer(-1), offer(1100),
        ])
        bot = AsyncMock()
        await search.check_price_alerts(bot)
        bot.send_message.assert_not_awaited()

    async def test_one_failed_database_update_does_not_block_other_subscribers(self):
        bot = AsyncMock()
        with patch.object(self.repository, "mark_checked", side_effect=[OSError("DB busy"), None]) as mark:
            await search.check_price_alerts(bot)
        self.assertEqual(mark.call_count, 2)
        self.assertEqual(bot.send_message.await_count, 2)

    async def test_cheapest_matching_currency_used_even_when_not_first(self):
        self.service.search_all_sources_by_onliner_key.return_value = comparison([
            offer(300, "USD"), offer(950), offer(850),
        ])
        bot = AsyncMock()
        await search.check_price_alerts(bot)
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertTrue(all(alert.last_notified_price == 850 for alert in self.repository.active_alerts()))

    async def test_failed_history_write_does_not_block_notification(self):
        bot = AsyncMock()
        with patch.object(self.repository, "record_offers", side_effect=OSError("disk full")):
            await search.check_price_alerts(bot)
        self.assertEqual(bot.send_message.await_count, 2)

    async def test_background_loop_survives_one_failed_iteration(self):
        with patch.object(search, "check_price_alerts", AsyncMock(side_effect=[OSError("DB busy"), asyncio.CancelledError()])) as check:
            with self.assertRaises(asyncio.CancelledError):
                await search.run_price_alert_loop(AsyncMock(), 0)
        self.assertEqual(check.await_count, 2)


class ThousandConcurrentRequestsTest(unittest.IsolatedAsyncioTestCase):
    async def test_1000_distinct_requests_are_isolated_and_bounded(self):
        coordinator = SearchRequestCoordinator(max_concurrent=8, max_pending=1000)
        async def load(index):
            await asyncio.sleep(0)
            return f"product-{index}"
        results = await asyncio.gather(*(
            coordinator.run(f"query-{index}", lambda index=index: load(index))
            for index in range(1000)
        ))
        self.assertEqual(results, [f"product-{index}" for index in range(1000)])
        self.assertLessEqual(coordinator.peak_active, 8)
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.active_count, 0)

    async def test_1000_simultaneous_requests_fail_fast_at_production_capacity(self):
        coordinator = SearchRequestCoordinator(max_concurrent=8, max_pending=200)
        release = asyncio.Event()
        async def load():
            await release.wait()
            return "ok"
        tasks = [asyncio.create_task(coordinator.run(index, load)) for index in range(1000)]
        await asyncio.sleep(0)
        self.assertEqual(coordinator.pending_count, 200)
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(results.count("ok"), 200)
        self.assertEqual(sum(isinstance(result, SearchBusyError) for result in results), 800)
        self.assertEqual(coordinator.pending_count, 0)
        self.assertLessEqual(coordinator.peak_active, 8)

    async def test_1000_same_product_requests_share_one_loader(self):
        coordinator = SearchRequestCoordinator(max_concurrent=8, max_pending=200)
        loader = AsyncMock(return_value="same product")
        results = await asyncio.gather(*(coordinator.run("pixel8", loader) for _ in range(1000)))
        self.assertEqual(results, ["same product"] * 1000)
        loader.assert_awaited_once()
        self.assertEqual(coordinator.pending_count, 0)


if __name__ == "__main__":
    unittest.main()
