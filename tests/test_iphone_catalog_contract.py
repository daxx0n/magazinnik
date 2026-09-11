import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.handlers import search
from app.models.catalog import ExternalCatalogItem, ProductIdentity
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.catalog_relevance import is_catalog_record_relevant
from app.services.catalog_service import CatalogService
from app.services.selection_flow import ordered_variant_groups
from app.services.sqlite_catalog_storage import SqliteCatalogStorage
from app.services.unified_catalog import UnifiedCatalogPriceService


def candidate(key: str, title: str, category: str = "mobile") -> ProductCandidate:
    return ProductCandidate(
        key=key,
        title=title,
        url=f"https://catalog.example/{category}/{key}",
    )


def offer(source: str, key: str, title: str) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=1000,
        currency="BYN",
        available=True,
        url=f"https://{source}.example/product/{key}",
    )


class IphoneCatalogContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        catalog = CatalogService(
            storage=SqliteCatalogStorage(
                Path(self.directory.name) / "catalog.sqlite3"
            )
        )
        self.service = UnifiedCatalogPriceService(
            catalog,
            source_timeout=1,
        )
        self.addAsyncCleanup(self.service.close)

    def test_iphone_policy_rejects_accessories_used_and_fake_devices(self):
        rejected = (
            "Чехол для Apple iPhone 17 Pro Max",
            "Кабель USB-C для iPhone 16",
            "Защитное стекло Apple iPhone 15",
            "Apple iPhone 14 128GB б/у",
            "Смартфон Apple iPhone 13 восстановленный",
            "Муляж Apple iPhone 17",
            "Apple iPhone без указания модели",
        )
        for title in rejected:
            with self.subTest(title=title):
                self.assertFalse(
                    is_catalog_record_relevant("iphone", title)
                )

        accepted = (
            "Смартфон Apple iPhone 17 Pro Max 256GB Cosmic Orange",
            "Apple iPhone 16e 128GB Black",
            "Apple iPhone SE (2022) 64GB Midnight",
            "Apple iPhone XS Max 256GB Gold",
        )
        for title in accepted:
            with self.subTest(title=title):
                self.assertTrue(
                    is_catalog_record_relevant("iphone", title)
                )

    async def test_iphone_catalog_uses_all_sources_and_filters_old_junk(self):
        # Simulate pollution already persisted by the previous implementation.
        self.service._catalog_service.catalog.upsert(
            ExternalCatalogItem(
                source="legacy",
                external_id="case",
                title="Чехол для Apple iPhone 17",
                url="https://example.test/phonecase/case",
                identity=ProductIdentity(
                    brand="чехол",
                    model="для apple iphone 17",
                ),
            )
        )
        self.service._catalog_service.catalog.upsert(
            ExternalCatalogItem(
                source="Onliner",
                external_id="legacy-phone",
                title="Apple iPhone 12 64GB White",
                url="https://catalog.example/mobile/legacy-phone",
                identity=ProductIdentity(
                    brand="apple",
                    model="iphone 12",
                    memory="64GB",
                    color="white",
                ),
            )
        )

        self.service._onliner_source.find_products = AsyncMock(
            return_value=[
                candidate("17-black", "Apple iPhone 17 256GB Black"),
                candidate(
                    "17-case",
                    "Чехол для Apple iPhone 17",
                    category="phonecase",
                ),
            ]
        )
        self.service._five_element_source.find_products = AsyncMock(
            return_value=[
                candidate("16-blue", "Apple iPhone 16 128GB Blue"),
                candidate("16-used", "Apple iPhone 16 128GB Б/У"),
            ]
        )
        source_models = {
            "21vek": "Apple iPhone 15 128GB Green",
            "Shop.by": "Apple iPhone 14 Plus 256GB Purple",
            "Электросила": "Apple iPhone 13 mini 128GB Pink",
            "Zeon": "Apple iPhone SE (2022) 64GB Midnight",
        }
        for name, source in self.service._offer_sources():
            source.find_offers = AsyncMock(
                return_value=[
                    offer(name, "phone", source_models[name]),
                    offer(name, "cable", "Кабель для Apple iPhone 17"),
                ]
            )

        products = await self.service.find_products("iphone")
        titles = {product.title for product in products}

        self.assertEqual(
            titles,
            {
                "Apple iPhone 17 256GB Black",
                "Apple iPhone 16 128GB Blue",
                "Apple iPhone 12 64GB White",
                *source_models.values(),
            },
        )
        self.assertTrue(
            all(
                is_catalog_record_relevant("iphone", product.title, product.url)
                for product in products
            )
        )
        for expected_title in source_models.values():
            self.assertIn(expected_title, titles)
        self.service._onliner_source.find_products.assert_awaited_once_with(
            "iphone",
            limit=100,
        )
        self.service._five_element_source.find_products.assert_awaited_once_with(
            "iphone",
            limit=50,
        )
        for _, source in self.service._offer_sources():
            source.find_offers.assert_awaited_once_with("iphone", limit=50)

    async def test_iphone_ui_contract_is_model_then_memory_then_color(self):
        products = [
            candidate("17-128-black", "Apple iPhone 17 128GB Black"),
            candidate("17-256-black", "Apple iPhone 17 256GB Black"),
            candidate("17-256-blue", "Apple iPhone 17 256GB Deep Blue"),
            candidate("16-128-black", "Apple iPhone 16 128GB Black"),
        ]
        groups = ordered_variant_groups(
            products,
            search.group_model_variants,
        )
        self.assertEqual(
            [group.title for group in groups],
            ["Apple iPhone 17", "Apple iPhone 16"],
        )

        search_id = search.store_product_search(
            products,
            query="iphone",
            owner_chat_id=10,
            owner_user_id=20,
        )
        callback = AsyncMock()
        callback.data = f"olg:{search_id}:0"
        callback.message.chat.id = 10
        callback.from_user.id = 20
        await search.handle_variant_group(callback)
        self.assertIn("Выбери память", callback.message.edit_text.await_args.args[0])

        memory_groups = search.selectable_memory_groups(groups[0].products)
        selected_memory = next(
            index
            for index, (memory, _) in enumerate(memory_groups)
            if memory == "256GB"
        )
        callback.reset_mock()
        callback.data = f"olm:{search_id}:0:{selected_memory}"
        callback.message.chat.id = 10
        callback.from_user.id = 20
        await search.handle_memory_selection(callback)
        markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
        labels = [row[0].text for row in markup.inline_keyboard]
        self.assertTrue(any("Black" in label for label in labels))
        self.assertTrue(any("Deep Blue" in label for label in labels))

    async def test_selected_iphone_never_uses_accessory_or_used_price(self):
        title = "Apple iPhone 17 256GB Black"
        product = self.service._catalog_service.catalog.upsert(
            ExternalCatalogItem(
                source="Onliner",
                external_id="iphone-17",
                title=title,
                url="https://catalog.example/mobile/iphone-17",
                identity=ProductIdentity(
                    brand="apple",
                    model="iphone 17",
                    memory="256GB",
                    color="black",
                ),
            )
        )
        self.service._onliner_source.search_by_key = AsyncMock(
            return_value=[
                offer("Onliner", "phone", title),
                offer("Onliner", "case", "Чехол для Apple iPhone 17"),
            ]
        )
        self.service._five_element_source.find_products = AsyncMock(
            return_value=[]
        )
        for name, source in self.service._offer_sources():
            source.find_offers = AsyncMock(
                return_value=[
                    offer(name, "phone", title),
                    offer(name, "used", "Apple iPhone 17 256GB Black Б/У"),
                    offer(name, "glass", "Стекло для Apple iPhone 17"),
                ]
            )

        result = await self.service.search_all_sources_by_onliner_key(
            f"catalog:{product.key}",
            "iphone",
        )

        self.assertEqual(len(result.source_statuses), 6)
        self.assertTrue(
            all(
                is_catalog_record_relevant("iphone", item.title, item.url)
                for item in result.offers
            )
        )
        self.assertTrue(all(item.title == title for item in result.offers))

    async def test_handler_calls_source_independent_search_entrypoint(self):
        service = Mock()
        service.should_categorize_query.return_value = False
        service.find_products = AsyncMock(return_value=[
            candidate("17", "Apple iPhone 17 256GB Black")
        ])
        service.find_onliner_products = AsyncMock()
        message = AsyncMock()
        message.text = "iphone"
        message.chat.id = 10
        message.from_user.id = 20

        with patch.object(search, "price_service", service):
            await search.handle_search(message)

        service.find_products.assert_awaited_once_with(
            "iphone",
            category=None,
        )
        service.find_onliner_products.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
