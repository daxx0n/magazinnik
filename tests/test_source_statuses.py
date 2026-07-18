import asyncio
import unittest
from unittest.mock import AsyncMock

from app.models.category import ProductCategory
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import SourceSearchStatus
from app.handlers.search import (
    build_category_keyboard,
    build_product_keyboard,
    format_category_page_text,
    format_product_page_text,
    format_source_status,
    product_search_parents,
    show_comparison,
)
from app.services.price_service import PriceService
from app.sources import (
    ProductNotFoundError,
    SourceUnavailableError,
)
from app.sources.five_element import FiveElementSource


def make_offer(
    source: str,
    title: str,
    price: float,
) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url="https://example.com/product",
    )


class SourceStatusesTest(unittest.IsolatedAsyncioTestCase):
    def test_keeps_five_element_display_item_candidate(self) -> None:
        candidate = FiveElementSource._parse_candidate(
            {
                "id": "iphone-17-black",
                "name": "Apple iPhone 17 512GB Black",
                "link_url": "/products/iphone-17-black",
                "available": False,
            }
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(
            candidate.title,
            "Apple iPhone 17 512GB Black",
        )

    def test_bounds_five_element_candidate_cache(self) -> None:
        source = FiveElementSource()
        source._candidate_cache_size = 2

        for index in range(3):
            source._remember_candidate(
                ProductCandidate(
                    key=f"model-{index}",
                    title=f"Model {index}",
                    url=f"https://example.com/{index}",
                )
            )

        self.assertEqual(
            list(source._candidate_urls),
            ["model-1", "model-2"],
        )

    async def test_searches_five_element_with_color_variants(self) -> None:
        service = PriceService()
        canonical = "Apple iPhone 17 512GB (черный)"
        candidate = ProductCandidate(
            key="iphone-17-black",
            title="Apple iPhone 17 512GB Black",
            url="https://5element.by/products/iphone-17-black",
        )
        offer = make_offer("5 элемент", candidate.title, 3500)
        service._five_element_source.find_products = AsyncMock(
            side_effect=[[], [candidate], []]
        )
        service.search_five_element_key = AsyncMock(
            return_value=[offer]
        )

        offers, had_candidates, _ = (
            await service._search_five_element_by_query(
                query="Apple iPhone 17 512GB",
                canonical_title=canonical,
                requested_title="iPhone",
            )
        )

        self.assertEqual(offers, [offer])
        self.assertTrue(had_candidates)
        self.assertEqual(
            [
                call.kwargs
                for call in service._five_element_source
                .find_products.await_args_list
            ],
            [
                {
                    "query": "Apple iPhone 17 512GB черный",
                    "limit": 100,
                },
                {
                    "query": "Apple iPhone 17 512GB Black",
                    "limit": 100,
                },
                {
                    "query": "Apple iPhone 17 512GB",
                    "limit": 100,
                },
            ],
        )

    async def test_five_element_survives_partial_search_failure(
        self,
    ) -> None:
        service = PriceService()
        candidate = ProductCandidate(
            key="iphone-17-black",
            title="Apple iPhone 17 512GB Black",
            url="https://5element.by/products/iphone-17-black",
        )
        offer = make_offer("5 элемент", candidate.title, 3500)
        service._five_element_source.find_products = AsyncMock(
            side_effect=[
                SourceUnavailableError("timeout"),
                [candidate],
                [],
            ]
        )
        service.search_five_element_key = AsyncMock(
            return_value=[offer]
        )

        offers, had_candidates, _ = (
            await service._search_five_element_by_query(
                query="Apple iPhone 17 512GB",
                canonical_title=(
                    "Apple iPhone 17 512GB (черный)"
                ),
                requested_title="iPhone",
            )
        )

        self.assertEqual(offers, [offer])
        self.assertTrue(had_candidates)

    async def test_five_element_matches_deep_blue_alias(self) -> None:
        service = PriceService()
        canonical = (
            "Apple iPhone 17 Pro 256GB (глубокий синий)"
        )
        candidate = ProductCandidate(
            key="355063",
            title=(
                "Смартфон Apple iPhone 17 Pro 256GB "
                "Deep Blue (MG8J4KH/A)"
            ),
            url=(
                "https://5element.by/products/"
                "iphone-17-pro-256gb-deep-blue-telefon-gsm-apple-"
                "mg8j4kh-a"
            ),
        )
        offer = make_offer("5 элемент", candidate.title, 4899)
        service._five_element_source.find_products = AsyncMock(
            side_effect=[[], [candidate], []]
        )
        service.search_five_element_key = AsyncMock(
            return_value=[offer]
        )

        offers, had_candidates, _ = (
            await service._search_five_element_by_query(
                query="Apple iPhone 17 Pro 256GB",
                canonical_title=canonical,
                requested_title="iPhone 17 Pro",
            )
        )

        self.assertEqual(offers, [offer])
        self.assertTrue(had_candidates)

    async def test_searches_twenty_one_vek_with_color_variants(self) -> None:
        service = PriceService()
        offer = make_offer(
            "21vek",
            "Apple iPhone 17 512GB черный",
            3600,
        )
        service._twenty_one_vek_source.find_offers = AsyncMock(
            side_effect=[[offer], [], [offer]]
        )

        offers = await service._search_twenty_one_vek_by_query(
            query="Apple iPhone 17 512GB",
            canonical_title="Apple iPhone 17 512GB (черный)",
        )

        self.assertEqual(offers, [offer])
        self.assertEqual(
            [
                call.kwargs
                for call in service._twenty_one_vek_source
                .find_offers.await_args_list
            ],
            [
                {
                    "query": "Apple iPhone 17 512GB черный",
                    "limit": 100,
                },
                {
                    "query": "Apple iPhone 17 512GB Black",
                    "limit": 100,
                },
                {
                    "query": "Apple iPhone 17 512GB",
                    "limit": 100,
                },
            ],
        )

    async def test_twenty_one_vek_matches_deep_blue_alias(self) -> None:
        service = PriceService()
        offer = make_offer(
            "21vek",
            "Смартфон Apple iPhone 17 Pro 256GB (темно-синий)",
            4599,
        )
        service._twenty_one_vek_source.find_offers = AsyncMock(
            side_effect=[[], [offer], []]
        )

        offers = await service._search_twenty_one_vek_by_query(
            query="Apple iPhone 17 Pro 256GB",
            canonical_title=(
                "Apple iPhone 17 Pro 256GB (глубокий синий)"
            ),
        )

        self.assertEqual(offers, [offer])

    async def test_searches_shop_by_with_color_variants(self) -> None:
        service = PriceService()
        offer = make_offer(
            "Shop.by",
            "Apple iPhone 17 512GB Black",
            3400,
        )
        service._shop_by_source.find_offers = AsyncMock(
            side_effect=[[offer], [], [offer]]
        )

        offers = await service._search_shop_by_query(
            query="Apple iPhone 17 512GB",
            canonical_title="Apple iPhone 17 512GB (черный)",
        )

        self.assertEqual(offers, [offer])
        self.assertEqual(
            [
                call.kwargs
                for call in service._shop_by_source
                .find_offers.await_args_list
            ],
            [
                {
                    "query": "Apple iPhone 17 512GB черный",
                    "limit": 100,
                },
                {
                    "query": "Apple iPhone 17 512GB Black",
                    "limit": 100,
                },
                {
                    "query": "Apple iPhone 17 512GB",
                    "limit": 100,
                },
            ],
        )

    async def test_searches_electrosila_with_color_variants(self) -> None:
        service = PriceService()
        offer = make_offer(
            "Электросила",
            "Apple iPhone 17 512GB Black",
            3499,
        )
        service._electrosila_source.find_offers = AsyncMock(
            side_effect=[[offer], [], [offer]]
        )

        offers = await service._search_electrosila_query(
            query="Apple iPhone 17 512GB",
            canonical_title="Apple iPhone 17 512GB (черный)",
        )

        self.assertEqual(offers, [offer])
        self.assertEqual(
            [
                call.kwargs
                for call in service._electrosila_source
                .find_offers.await_args_list
            ],
            [
                {
                    "query": "Apple iPhone 17 512GB черный",
                    "limit": 30,
                },
                {
                    "query": "Apple iPhone 17 512GB Black",
                    "limit": 30,
                },
                {
                    "query": "Apple iPhone 17 512GB",
                    "limit": 30,
                },
            ],
        )

    async def test_searches_zeon_once_by_base_model(self) -> None:
        service = PriceService()
        offer = make_offer(
            "Zeon",
            "Apple iPhone 17 512GB (черный)",
            3399,
        )
        service._zeon_source.find_offers = AsyncMock(
            return_value=[offer]
        )

        offers = await service._search_zeon_query(
            query="Apple iPhone 17 512GB",
            canonical_title="Apple iPhone 17 512GB (черный)",
        )

        self.assertEqual(offers, [offer])
        self.assertEqual(
            service._zeon_source.find_offers.await_count,
            3,
        )

    async def test_reuses_recent_external_search_results(self) -> None:
        service = PriceService()
        offer = make_offer(
            "21vek",
            "Apple iPhone 17 512GB Black",
            3500,
        )
        service._twenty_one_vek_source.find_offers = AsyncMock(
            return_value=[offer]
        )

        for _ in range(2):
            result = await service._search_twenty_one_vek_by_query(
                query="Apple iPhone 17 512GB",
                canonical_title=(
                    "Apple iPhone 17 512GB (черный)"
                ),
            )
            self.assertEqual(result, [offer])

        self.assertEqual(
            service._twenty_one_vek_source.find_offers.await_count,
            3,
        )

    async def test_coalesces_simultaneous_external_searches(
        self,
    ) -> None:
        service = PriceService()
        offer = make_offer("Shop.by", "Phone Black", 1000)

        async def delayed_search(**kwargs) -> list[ProductOffer]:
            await asyncio.sleep(0.01)
            return [offer]

        service._shop_by_source.find_offers = AsyncMock(
            side_effect=delayed_search
        )

        results = await asyncio.gather(
            *(
                service._search_shop_by_query(
                    query="Phone 256GB",
                    canonical_title="Phone 256GB (Black)",
                )
                for _ in range(2)
            )
        )

        self.assertEqual(results, [[offer], [offer]])
        self.assertEqual(
            service._shop_by_source.find_offers.await_count,
            2,
        )

    async def test_does_not_cache_external_search_errors(self) -> None:
        service = PriceService()
        service._shop_by_source.find_offers = AsyncMock(
            side_effect=SourceUnavailableError("timeout")
        )

        for _ in range(2):
            with self.assertRaises(SourceUnavailableError):
                await service._search_shop_by_query(
                    query="Phone 256GB",
                    canonical_title="Phone 256GB (Black)",
                )

        self.assertEqual(
            service._shop_by_source.find_offers.await_count,
            4,
        )

    async def test_cancelled_waiter_does_not_cancel_shared_search(
        self,
    ) -> None:
        service = PriceService()
        offer = make_offer("Shop.by", "Phone", 1000)
        started = asyncio.Event()
        release = asyncio.Event()
        loader_calls = 0

        async def loader() -> list[ProductOffer]:
            nonlocal loader_calls
            loader_calls += 1
            started.set()
            await release.wait()
            return [offer]

        waiter = asyncio.create_task(
            service._cached_source_search(
                source_name="test",
                query="Phone",
                limit=100,
                loader=loader,
            )
        )
        await started.wait()
        waiter.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await waiter

        release.set()
        result = await service._cached_source_search(
            source_name="test",
            query="Phone",
            limit=100,
            loader=loader,
        )

        self.assertEqual(result, [offer])
        self.assertEqual(loader_calls, 1)
        self.assertEqual(service._source_search_tasks, {})

    def test_keeps_only_cheapest_offer_per_source(self) -> None:
        offers = [
            make_offer("Onliner", "Model", 1200),
            make_offer("Onliner", "Model", 1100),
            make_offer("5 элемент", "Model", 1300),
            make_offer("21vek", "Model", 1250),
            make_offer("Shop.by", "Model", 1150),
            make_offer("Shop.by", "Model", 1175),
            make_offer("Электросила", "Model", 1125),
            make_offer("Электросила", "Model", 1140),
            make_offer("Zeon", "Model", 1075),
            make_offer("Zeon", "Model", 1090),
        ]

        result = PriceService._prepare_aggregate_offers(
            offers
        )

        self.assertEqual(
            [(offer.source, offer.price) for offer in result],
            [
                ("Zeon", 1075),
                ("Onliner", 1100),
                ("Электросила", 1125),
                ("Shop.by", 1150),
                ("21vek", 1250),
                ("5 элемент", 1300),
            ],
        )

    async def test_renders_sorted_source_comparison_and_colors(
        self,
    ) -> None:
        offers = [
            ProductOffer(
                source=source,
                title=(
                    "Apple iPhone 17 512GB (синий)"
                    if source == "Onliner"
                    else "Apple iPhone 17 512GB Mist Blue"
                ),
                price=price,
                currency="BYN",
                available=True,
                url=f"https://example.com/{index}",
                seller=("Seller" if source == "Onliner" else source),
            )
            for index, (source, price) in enumerate(
                [
                    ("Zeon", 3200),
                    ("Электросила", 3300),
                    ("Shop.by", 3400),
                    ("Onliner", 3500),
                    ("21vek", 3600),
                    ("5 элемент", 3700),
                ]
            )
        ]
        message = AsyncMock()

        await show_comparison(message, offers)

        text = message.edit_text.await_args.args[0]
        self.assertIn("Найдено предложений: 6", text)
        self.assertIn(
            "📱 Apple iPhone 17 512GB (Mist Blue)",
            text,
        )
        self.assertLess(
            text.index("1. Zeon"),
            text.index("2. Электросила"),
        )
        self.assertLess(
            text.index("2. Электросила"),
            text.index("3. Shop.by"),
        )
        self.assertEqual(text.count("🔗 https://example.com/"), 6)

    def test_paginates_product_variants(self) -> None:
        products = [
            ProductCandidate(
                key=f"model-{index}",
                title=f"Model {index}",
                url=f"https://example.com/{index}",
            )
            for index in range(23)
        ]

        keyboard = build_product_keyboard(
            products=products,
            search_id="search",
            page=1,
        )
        rows = keyboard.inline_keyboard

        self.assertEqual(len(rows), 11)
        self.assertEqual(
            rows[0][0].callback_data,
            "ol:model-10",
        )
        self.assertEqual(
            rows[9][0].callback_data,
            "ol:model-19",
        )
        self.assertEqual(
            [button.text for button in rows[-1]],
            [
                "⏮ В начало",
                "⬅️ Назад",
                "Далее ➡️",
            ],
        )
        self.assertEqual(
            format_product_page_text(23, 1),
            "Нашёл вариантов: 23.\n"
            "Страница 2 из 3.\n\n"
            "Выбери точную модель:",
        )

    def test_paginates_categories_and_returns_from_products(self) -> None:
        categories = [
            ProductCategory(
                key=f"category-{index}",
                title=f"Категория {index}",
            )
            for index in range(23)
        ]

        keyboard = build_category_keyboard(
            categories=categories,
            search_id="categories",
            page=1,
        )
        rows = keyboard.inline_keyboard

        self.assertEqual(rows[0][0].callback_data, "olc:categories:10")
        self.assertEqual(
            [button.text for button in rows[-1]],
            ["⏮ В начало", "⬅️ Назад", "Далее ➡️"],
        )
        self.assertEqual(
            format_category_page_text("Samsung", 23, 1),
            "Запрос «Samsung» относится к нескольким "
            "категориям.\n"
            "Страница 2 из 3.\n\n"
            "Сначала выбери тип товара:",
        )

        products = [
            ProductCandidate(
                key="model",
                title="Model",
                url="https://example.com/model",
            )
        ]
        product_search_parents["products"] = ("categories", 1)

        try:
            product_keyboard = build_product_keyboard(
                products=products,
                search_id="products",
                page=0,
            )
        finally:
            product_search_parents.pop("products", None)

        self.assertEqual(
            product_keyboard.inline_keyboard[-1][0].callback_data,
            "olcp:categories:1",
        )

    async def test_continues_when_onliner_has_no_offers(self) -> None:
        service = PriceService()
        canonical = "LG OLED C4 OLED55C4RLA"
        service._onliner_candidates["oled55c4rla"] = (
            ProductCandidate(
                key="oled55c4rla",
                title=canonical,
                url="https://example.com/onliner",
            )
        )
        service.search_onliner_key = AsyncMock(
            side_effect=ProductNotFoundError(
                "Нет продавцов"
            )
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=(
                [make_offer("5 элемент", canonical, 3000)],
                True,
                [],
            )
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[]
        )
        service._search_shop_by_query = AsyncMock(
            return_value=[]
        )
        service._search_electrosila_query = AsyncMock(
            return_value=[]
        )
        service._search_zeon_query = AsyncMock(
            return_value=[]
        )

        result = (
            await service.search_all_sources_by_onliner_key(
                "oled55c4rla"
            )
        )

        self.assertEqual(len(result.offers), 1)
        self.assertEqual(result.offers[0].source, "5 элемент")
        self.assertEqual(
            [status.state for status in result.source_statuses],
            [
                "not_found",
                "found",
                "not_found",
                "not_found",
                "not_found",
                "not_found",
            ],
        )

    async def test_continues_when_onliner_is_unavailable(self) -> None:
        service = PriceService()
        canonical = "LG OLED C4 OLED55C4RLA"
        service._onliner_candidates["oled55c4rla"] = (
            ProductCandidate(
                key="oled55c4rla",
                title=canonical,
                url="https://example.com/onliner",
            )
        )
        service.search_onliner_key = AsyncMock(
            side_effect=SourceUnavailableError("timeout")
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=(
                [make_offer("5 элемент", canonical, 3000)],
                True,
                [],
            )
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[]
        )
        service._search_shop_by_query = AsyncMock(
            return_value=[]
        )
        service._search_electrosila_query = AsyncMock(
            return_value=[]
        )
        service._search_zeon_query = AsyncMock(
            return_value=[]
        )

        result = await service.search_all_sources_by_onliner_key(
            "oled55c4rla"
        )

        self.assertEqual(result.offers[0].source, "5 элемент")
        self.assertEqual(
            result.source_statuses[0].state,
            "unavailable",
        )

    async def test_searches_all_sources_concurrently(self) -> None:
        service = PriceService()
        canonical = "Apple iPhone 17 512GB (черный)"
        service._onliner_candidates["iphone17"] = ProductCandidate(
            key="iphone17",
            title=canonical,
            url="https://example.com/onliner",
        )
        active_requests = 0
        max_active_requests = 0

        def delayed(result):
            async def call(*args, **kwargs):
                nonlocal active_requests, max_active_requests
                active_requests += 1
                max_active_requests = max(
                    max_active_requests,
                    active_requests,
                )
                await asyncio.sleep(0.01)
                active_requests -= 1
                return result

            return call

        service.search_onliner_key = AsyncMock(
            side_effect=delayed(
                [make_offer("Onliner", canonical, 3500)]
            )
        )
        service._search_five_element_by_query = AsyncMock(
            side_effect=delayed(([], False, []))
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            side_effect=delayed([])
        )
        service._search_shop_by_query = AsyncMock(
            side_effect=delayed([])
        )
        service._search_electrosila_query = AsyncMock(
            side_effect=delayed([])
        )
        service._search_zeon_query = AsyncMock(
            side_effect=delayed([])
        )

        await service.search_all_sources_by_onliner_key("iphone17")

        self.assertEqual(max_active_requests, 6)

    async def test_reports_every_checked_source(self) -> None:
        service = PriceService()
        canonical = "Духовой шкаф Bosch HBA534EB3"

        service.search_onliner_key = AsyncMock(
            return_value=[
                make_offer("Onliner", canonical, 1500),
                make_offer("Onliner", canonical, 1550),
            ]
        )
        service._onliner_queries["bosch-hba534eb3"] = (
            "Bosch HBA534EB3"
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=([], True, [])
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[]
        )
        service._search_shop_by_query = AsyncMock(
            return_value=[
                make_offer("Shop.by", canonical, 1400)
            ]
        )
        service._search_electrosila_query = AsyncMock(
            return_value=[
                make_offer("Электросила", canonical, 1450)
            ]
        )
        service._search_zeon_query = AsyncMock(
            return_value=[
                make_offer("Zeon", canonical, 1350)
            ]
        )

        result = (
            await service.search_all_sources_by_onliner_key(
                "bosch-hba534eb3"
            )
        )

        self.assertEqual(
            [status.source for status in result.source_statuses],
            [
                "Onliner",
                "5 элемент",
                "21vek",
                "Shop.by",
                "Электросила",
                "Zeon",
            ],
        )
        self.assertEqual(
            [status.state for status in result.source_statuses],
            [
                "found",
                "filtered",
                "not_found",
                "found",
                "found",
                "found",
            ],
        )
        self.assertEqual(
            [
                status.checked_candidates
                for status in result.source_statuses
            ],
            [2, 0, 0, 1, 1, 1],
        )
        self.assertTrue(
            all(
                status.duration_seconds >= 0
                for status in result.source_statuses
            )
        )
        self.assertEqual(result.query, "Bosch HBA534EB3")
        self.assertEqual(result.product_title, canonical)
        self.assertGreaterEqual(result.duration_seconds, 0)
        service._search_five_element_by_query.assert_awaited_once_with(
            query="Духовой шкаф Bosch HBA534EB3",
            canonical_title=canonical,
            requested_title="Bosch HBA534EB3",
        )
        service._search_twenty_one_vek_by_query.assert_awaited_once_with(
            query="Духовой шкаф Bosch HBA534EB3",
            canonical_title=canonical,
        )
        service._search_shop_by_query.assert_awaited_once_with(
            query="Духовой шкаф Bosch HBA534EB3",
            canonical_title=canonical,
        )
        service._search_electrosila_query.assert_awaited_once_with(
            query="Духовой шкаф Bosch HBA534EB3",
            canonical_title=canonical,
        )
        service._search_zeon_query.assert_awaited_once_with(
            query="Духовой шкаф Bosch HBA534EB3",
            canonical_title=canonical,
        )

    async def test_bounds_onliner_candidate_cache(self) -> None:
        service = PriceService()
        service._candidate_cache_size = 2
        service._onliner_source.find_products = AsyncMock(
            return_value=[
                ProductCandidate(
                    key=f"model-{index}",
                    title=f"Model {index}",
                    url=f"https://example.com/{index}",
                )
                for index in range(3)
            ]
        )

        await service.find_onliner_products("Model")

        self.assertEqual(
            list(service._onliner_candidates),
            ["model-1", "model-2"],
        )
        self.assertEqual(
            list(service._onliner_queries),
            ["model-1", "model-2"],
        )

    def test_formats_all_status_variants(self) -> None:
        cases = [
            (
                SourceSearchStatus("Onliner", "found", 5),
                "✅ Onliner — предложение найдено",
            ),
            (
                SourceSearchStatus("5 элемент", "filtered"),
                "⚠️ 5 элемент — варианты найдены, но не "
                "совпали с выбранной моделью",
            ),
            (
                SourceSearchStatus("21vek", "not_found"),
                "➖ 21vek — точная модель не найдена",
            ),
            (
                SourceSearchStatus("21vek", "unavailable"),
                "❌ 21vek — временно недоступен",
            ),
        ]

        for status, expected in cases:
            with self.subTest(state=status.state):
                self.assertEqual(
                    format_source_status(status),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
