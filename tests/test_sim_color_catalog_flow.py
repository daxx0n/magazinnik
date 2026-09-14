import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.handlers import search
from app.models.catalog import ExternalCatalogItem, ProductIdentity
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.catalog_service import CatalogService
from app.services.selection_presentation import (
    group_selection_model_variants,
    selection_color_key,
    selection_color_label,
)
from app.services.sim_selection import sim_groups
from app.services.sqlite_catalog_storage import SqliteCatalogStorage
from app.services.unified_catalog import UnifiedCatalogPriceService


def candidate(key, title):
    return ProductCandidate(key=key, title=title, url=f"https://example.test/{key}")


def offer(source, title, price=1000):
    return ProductOffer(source=source, title=title, price=price, currency="BYN",
                        available=True, url=f"https://example.test/{source}/{price}")


class SimColorPresentationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        search.product_searches.clear()
        search.product_search_parents.clear()

    def tearDown(self):
        search.product_searches.clear()
        search.product_search_parents.clear()

    def test_three_sim_variants_are_one_model(self):
        products = [
            candidate("base", "Apple iPhone 17 256GB Black"),
            candidate("sim", "Apple iPhone 17 Dual SIM 256GB Black"),
            candidate("esim", "Apple iPhone 17 Dual eSIM 256GB Black"),
        ]
        groups = group_selection_model_variants(products)
        self.assertEqual([(group.title, len(group.products)) for group in groups],
                         [("Apple iPhone 17", 3)])
        self.assertEqual([key for key, _ in sim_groups(groups[0].products)],
                         ["dual_sim", "dual_esim", "unknown"])

    async def test_sim_screen_offers_any_and_every_configuration(self):
        products = [
            candidate("base", "Apple iPhone 17 256GB Black"),
            candidate("sim", "Apple iPhone 17 Dual SIM 256GB Black"),
            candidate("esim", "Apple iPhone 17 Dual eSIM 256GB Black"),
        ]
        group = group_selection_model_variants(products)[0]
        message = AsyncMock()
        shown = await search.show_sim_selection(message, group, products, "session", 0, "all")
        self.assertTrue(shown)
        labels = [row[0].text for row in message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard]
        self.assertEqual(labels, ["💰 Любая SIM — найти дешевле", "Dual SIM",
                                  "Dual eSIM", "SIM не указана продавцом", "⬅️ Назад"])

    async def test_iphone_handler_opens_sim_inside_one_model(self):
        products = [
            candidate("base", "Apple iPhone 17 256GB Black"),
            candidate("sim", "Apple iPhone 17 Dual SIM 256GB Black"),
            candidate("esim", "Apple iPhone 17 Dual eSIM 256GB Black"),
        ]
        search_id = search.store_product_search(
            products, query="iPhone", owner_chat_id=10, owner_user_id=20,
        )
        callback = AsyncMock()
        callback.data = f"olg:{search_id}:0"
        callback.message.chat.id = 10
        callback.from_user.id = 20
        await search.handle_variant_group(callback)
        text = callback.message.edit_text.await_args.args[0]
        self.assertIn("Apple iPhone 17", text)
        self.assertIn("SIM-конфигурацию", text)
        self.assertNotIn("Dual SIM ·", text.splitlines()[0])

    async def test_same_color_across_sim_variants_uses_subset_callback(self):
        products = [
            candidate("sim", "Apple iPhone 17 Dual SIM 256GB Black"),
            candidate("esim", "Apple iPhone 17 Dual eSIM 256GB Black"),
        ]
        message = AsyncMock()
        message.chat.id = 10
        await search.show_color_selection(
            message, group_selection_model_variants(products)[0], products,
            "back", original_query="iPhone 17", user_id=20,
        )
        callback = message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
        self.assertTrue(callback.startswith("olv:"))
        self.assertEqual(len(search.product_searches[callback.split(":")[1]]), 2)

    def test_new_marketing_colors_are_exact_and_not_collapsed(self):
        titles = [
            "Apple iPhone 17 256GB Cosmic Orange",
            "Apple iPhone 17 256GB Deep Blue",
            "Apple iPhone 17 256GB Mist Blue",
        ]
        self.assertEqual([selection_color_key(title) for title in titles],
                         ["cosmic_orange", "deep_blue", "mist_blue"])
        self.assertEqual([selection_color_label(title) for title in titles],
                         ["Cosmic Orange", "Deep Blue", "Mist Blue"])

    def test_new_colors_work_for_phone_brands_without_static_palette(self):
        cases = {
            "OnePlus 13 256GB Arctic Dawn": "name:arctic_dawn",
            "Honor Magic7 512GB Lunar Shadow": "name:lunar_shadow",
            "Motorola Edge 60 256GB Pantone Gibraltar Sea": (
                "name:pantone_gibraltar_sea"
            ),
            "Nothing Phone 3 512GB Essential Space": "name:essential_space",
        }
        self.assertEqual(
            {title: selection_color_key(title) for title in cases},
            cases,
        )

    def test_technical_suffix_is_not_invented_as_color(self):
        for title in (
            "Apple iPhone 17 256GB Dual eSIM",
            "Apple iPhone 17 256GB Global version",
            "Apple iPhone 17 256GB EU",
        ):
            self.assertIsNone(selection_color_key(title))


class PersistentUnifiedCatalogTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "catalog.sqlite3"
        self.catalog = CatalogService(storage=SqliteCatalogStorage(self.path))
        self.service = UnifiedCatalogPriceService(self.catalog, source_timeout=1)
        self.addAsyncCleanup(self.service.close)

    async def test_discovery_combines_six_sources_and_persists(self):
        title = "Apple iPhone 17 Dual SIM 256GB Cosmic Orange"
        self.service._onliner_source.find_products = AsyncMock(return_value=[candidate("onliner-key", title)])
        self.service._five_element_source.find_products = AsyncMock(return_value=[candidate("five-key", title)])
        for name, source in self.service._offer_sources():
            source.find_offers = AsyncMock(return_value=[offer(name, title)])
        await self.service.discover("iPhone 17")
        restored = CatalogService(storage=SqliteCatalogStorage(self.path))
        products = restored.search("iPhone 17")
        self.assertEqual(len(products), 1)
        self.assertEqual({item.source for item in products[0].offers},
                         {"Onliner", "5 элемент", "21vek", "Shop.by", "Электросила", "Zeon"})

    async def test_local_hit_returns_immediately_and_completes_in_background(self):
        self.catalog.catalog.upsert(ExternalCatalogItem(
            source="fixture", external_id="1", title="Apple iPhone 17 256GB Black",
            url="https://example.test/1", identity=ProductIdentity(
                brand="apple", model="iphone 17", memory="256GB", color="black"),
        ))
        completed = asyncio.Event()

        async def discover(query):
            completed.set()

        self.service.discover = AsyncMock(side_effect=discover)
        products = await self.service.find_onliner_products("iPhone 17")
        self.assertEqual(len(products), 1)
        await completed.wait()
        self.service.discover.assert_awaited_once_with("iPhone 17")

    async def test_duplicate_discovery_is_coalesced(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def load(*args, **kwargs):
            started.set()
            await release.wait()
            return []
        self.service._onliner_source.find_products = load
        self.service._five_element_source.find_products = load
        for _, source in self.service._offer_sources():
            source.find_offers = load
        tasks = [asyncio.create_task(self.service.discover("same")) for _ in range(20)]
        await started.wait()
        self.assertEqual(len(self.service._discovery_tasks), 1)
        release.set()
        await asyncio.gather(*tasks)

    async def test_automatic_discovery_is_disabled_by_default(self):
        self.assertFalse(self.service.auto_discovery_enabled)
        self.service.discover = AsyncMock()

        await self.service.run_discovery_loop(interval=30)

        self.service.discover.assert_not_awaited()

    async def test_automatic_discovery_can_be_explicitly_enabled(self):
        service = UnifiedCatalogPriceService(
            self.catalog,
            auto_discovery_enabled=True,
        )
        self.addAsyncCleanup(service.close)

        self.assertTrue(service.auto_discovery_enabled)

    async def test_comparison_checks_six_sources_and_filters_wrong_variant(self):
        title = "Apple iPhone 17 Dual SIM 256GB Cosmic Orange"
        item = self.catalog.catalog.upsert(ExternalCatalogItem(
            source="Onliner", external_id="onliner-key", title=title,
            url="https://example.test/onliner", identity=ProductIdentity(
                brand="apple", model="iphone 17 dual sim", memory="256GB",
                color="cosmic_orange"),
        ))
        self.service._onliner_source.search_by_key = AsyncMock(return_value=[
            offer("Onliner", title, 1100),
        ])
        self.service._five_element_source.find_products = AsyncMock(return_value=[])
        for name, source in self.service._offer_sources():
            source.find_offers = AsyncMock(return_value=[
                offer(name, title, 900),
                offer(name, "Apple iPhone 17 Dual eSIM 256GB Cosmic Orange", 100),
                offer(name, "Apple iPhone 17 Dual SIM 256GB Deep Blue", 200),
            ])
        result = await self.service.search_all_sources_by_onliner_key(
            f"catalog:{item.key}", "iPhone 17",
        )
        self.assertEqual(len(result.source_statuses), 6)
        self.assertEqual({entry.source for entry in result.source_statuses},
                         {"Onliner", "5 элемент", "21vek", "Shop.by", "Электросила", "Zeon"})
        self.assertTrue(all("Dual eSIM" not in entry.title and "Deep Blue" not in entry.title
                            for entry in result.offers))
        self.assertEqual(result.offers[0].price, 900)

    async def test_fresh_comparison_does_not_repeat_retailer_requests(self):
        title = "Google Pixel 9 Pro 256GB Obsidian"
        product = self.catalog.catalog.upsert(ExternalCatalogItem(
            source="Onliner", external_id="pixel-9", title=title,
            url="https://example.test/pixel-9", price=2999, currency="BYN",
            identity=ProductIdentity(brand="google", model="pixel 9 pro",
                                     memory="256GB", color="black"),
        ))
        self.service._onliner_source.search_by_key = AsyncMock()
        self.service._five_element_source.find_products = AsyncMock()
        for _, source in self.service._offer_sources():
            source.find_offers = AsyncMock()

        result = await self.service.search_all_sources_by_onliner_key(
            f"catalog:{product.key}",
            "Google Pixel 9 Pro",
        )

        self.assertEqual([item.price for item in result.offers], [2999])
        self.service._onliner_source.search_by_key.assert_not_awaited()
        self.service._five_element_source.find_products.assert_not_awaited()
        for _, source in self.service._offer_sources():
            source.find_offers.assert_not_awaited()

    async def test_cache_is_labeled_only_when_all_sources_fail(self):
        title = "Apple iPhone 17 Dual SIM 256GB Black"
        product = self.catalog.catalog.upsert(ExternalCatalogItem(
            source="Onliner", external_id="key", title=title,
            url="https://example.test/onliner", price=999, currency="BYN",
            identity=ProductIdentity(brand="apple", model="iphone 17 dual sim",
                                     memory="256GB", color="black"),
            updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ))
        async def failed(*args, **kwargs):
            raise RuntimeError("offline")
        self.service._onliner_source.search_by_key = failed
        self.service._five_element_source.find_products = failed
        for _, source in self.service._offer_sources():
            source.find_offers = failed
        result = await self.service.search_all_sources_by_onliner_key(f"catalog:{product.key}")
        self.assertEqual(len(result.offers), 1)
        self.assertIn("Сохранённая цена", result.offers[0].availability_text)
        self.assertTrue(all(status.state == "unavailable" for status in result.source_statuses))


if __name__ == "__main__":
    unittest.main()
