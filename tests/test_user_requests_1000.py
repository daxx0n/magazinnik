"""Exactly 1,000 distinct text requests through the real Telegram search handler.

No Telegram or retailer traffic: fresh in-memory catalog, mocked transport and
explicit offline fallback. Every request has an expected outcome, not just a
no-exception assertion. Run with unittest discovery; generated IDs are stable.
"""
import unittest
from collections import OrderedDict
from unittest.mock import AsyncMock, Mock, patch

from app.handlers import search
from app.models.catalog import ExternalCatalogItem, ProductIdentity
from app.models.category import ProductCategory
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.catalog_service import CatalogService
from app.services.search_load import SearchBusyError, SearchRequestCoordinator
from app.services.search_sessions import SearchSessionRegistry, SelectionQueryRegistry
from app.sources import SourceUnavailableError


MODELS = [
    ("Apple", "iPhone 15"), ("Apple", "iPhone 15 Pro"),
    ("Apple", "iPhone 16"), ("Apple", "iPhone 16 Pro Max"),
    ("Google", "Pixel 8"), ("Google", "Pixel 9 Pro"),
    ("Samsung", "Galaxy S24"), ("Samsung", "Galaxy S25 Ultra"),
    ("Xiaomi", "Redmi Note 13"), ("Huawei", "Nova 12"),
]


def requests():
    cases = []
    for brand, model in MODELS:
        for memory in ("128GB", "256GB", "512GB"):
            for color in ("Black", "White"):
                title = f"{brand} {model} {memory} {color}"
                for style in range(10):
                    words = (title.upper() if style % 2 else title.lower()).split()
                    separator = (" ", "  ", "\t", "\n", "\u00a0")[style // 2]
                    query = separator.join(words)
                    cases.append(("catalog", query, (brand, model, memory, color, title)))
    for index in range(50):
        cases.append(("invalid", chr(0x410 + index // 32) + chr(0x410 + index % 32), None))
        cases.append(("invalid", f"Pixel {index} " + "x" * 201, None))
    for index in range(100):
        cases.append(("empty", f"несуществующий товар ZZ{index:04d}", None))
        cases.append(("failure", f"Samsung Galaxy offline {index:04d}", index % 3))
        cases.append(("category", f"аксессуары серия {index:04d}", None))
    assert len(cases) == len({case[1] for case in cases}) == 1000
    return cases


CASES = requests()


class UserRequests1000Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network is forbidden in request simulation")))
        # All mutable process registries are fresh per user scenario.
        for name in ("product_searches", "category_searches", "comparison_diagnostics"):
            self.enterContext(patch.object(search, name, OrderedDict()))
        self.enterContext(patch.object(search, "product_search_parents", {}))
        for name in ("product_session_registry", "category_session_registry"):
            self.enterContext(patch.object(search, name, SearchSessionRegistry(capacity=1000, ttl_seconds=1800)))
        self.enterContext(patch.object(search, "selection_query_registry", SelectionQueryRegistry(capacity=1000, ttl_seconds=1800)))
        for name in ("product_discovery_coordinator", "category_discovery_coordinator"):
            self.enterContext(patch.object(search, name, SearchRequestCoordinator()))
        self.enterContext(patch.dict("os.environ", {"SEARCH_MAX_QUERY_LENGTH": "200"}))
        self.message = AsyncMock()
        self.message.chat.id = 101
        self.message.from_user.id = 202

    async def run_case(self, kind, query, payload):
        self.message.text = query
        service = Mock()
        service.should_categorize_query.return_value = False
        service.find_onliner_products = AsyncMock(return_value=[])
        service.find_onliner_categories = AsyncMock(return_value=[])
        expected_key = None
        if kind == "catalog":
            brand, model, memory, color, title = payload
            # No storage environment or production data are consulted.
            with patch.object(CatalogService, "_storage_from_environment", return_value=None):
                catalog = CatalogService()
            product = catalog.catalog.upsert(ExternalCatalogItem(
                source="fixture", external_id=title, title=title,
                url="https://example.test/product", price=1000, currency="BYN",
                identity=ProductIdentity(brand=brand, model=model, memory=memory, color=color),
            ))
            expected_key = f"catalog:{product.key}"
            service = CatalogFirstPriceService(catalog_service=catalog, catalog_search_enabled=True)
            service.should_categorize_query = Mock(return_value=False)
            service._onliner_source.find_products = AsyncMock(side_effect=AssertionError("Unexpected live fallback"))
        elif kind == "failure":
            service.find_onliner_products.side_effect = (
                SourceUnavailableError("offline"), SearchBusyError("full"), RuntimeError("fixture failure")
            )[payload]
        elif kind == "category":
            service.should_categorize_query.return_value = True
            service.find_onliner_categories.return_value = [
                ProductCategory(key="mobile", title="Смартфоны"),
                ProductCategory(key="tablet", title="Планшеты"),
            ]
        with patch.object(search, "price_service", service), patch.object(search, "logger"):
            await search.handle_search(self.message)
        status = self.message.answer.return_value
        if kind == "invalid":
            self.message.answer.assert_awaited_once()
            self.assertIn("Название слишком", self.message.answer.call_args.args[0])
            service.find_onliner_products.assert_not_awaited()
            status.edit_text.assert_not_awaited()
        elif kind == "catalog":
            self.assertEqual(len(search.product_searches), 1)
            products = next(iter(search.product_searches.values()))
            self.assertEqual([product.key for product in products], [expected_key])
            service._onliner_source.find_products.assert_not_awaited()
            markup = status.edit_text.call_args.kwargs["reply_markup"]
            self.assertTrue(markup.inline_keyboard)
            for row in markup.inline_keyboard:
                for button in row:
                    self.assertLessEqual(len(button.callback_data.encode()), 64)
        elif kind == "empty":
            self.assertIn("не найдены", status.edit_text.call_args.args[0])
            self.assertFalse(search.product_searches)
        elif kind == "failure":
            expected = ("временно недоступен", "слишком много", "ошибка при поиске")[payload]
            self.assertIn(expected, status.edit_text.call_args.args[0])
            self.assertFalse(search.product_searches)
        else:
            self.assertEqual(len(search.category_searches), 1)
            session = next(iter(search.category_searches.values()))
            self.assertEqual(session.query, query)
            self.assertEqual(len(session.categories), 2)
            service.find_onliner_products.assert_not_awaited()


def make_test(case):
    async def test(self):
        await self.run_case(*case)
    test.__doc__ = f"{case[0]}: {case[1]!r}"
    return test


for index, case in enumerate(CASES, 1):
    setattr(UserRequests1000Test, f"test_request_{index:04d}_{case[0]}", make_test(case))


if __name__ == "__main__":
    unittest.main()
