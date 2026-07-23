import unittest
from unittest.mock import AsyncMock, Mock

from app.models.offer import ProductOffer
from app.services.catalog_first_search import CatalogFirstPriceService
from app.sources.zeon import ZeonSource


CANONICAL_TITLE = (
    'Xiaomi TV A Pro 50" 2026 L50MB-APRU '
    '(международная версия)'
)
ZEON_TITLE = "Телевизор " + CANONICAL_TITLE
PRODUCT_URL = (
    "https://www.zeon.by/product/"
    "1814419-xiaomi-tv-a-pro-50-2026-l50mb-apru-mezhdunarodnaya-versiya/"
)


def product_page(title: str = ZEON_TITLE, price: str = "1070.10") -> str:
    return f"""
    <main>
      <h1 itemprop="name">{title}</h1>
      <div itemprop="offers">
        <link itemprop="availability" href="http://schema.org/InStock">
        <meta itemprop="price" content="{price}">
      </div>
      <div id="delivery-tab-1">
        <p><strong class="color-green">25.07.2026</strong></p>
      </div>
    </main>
    """


def search_card(title: str, path: str, price: str = "999,00") -> str:
    return f"""
    <div class="catalog-item">
      <div class="catalog-item-title">
        <a href="https://www.zeon.by/product/{path}/">{title}</a>
      </div>
      <span class="catalog-item-stock instock">В наличии</span>
      <div class="catalog-item-price">{price} руб</div>
    </div>
    """


def offer(source: str, title: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{source.casefold()}",
        seller=source,
    )


class ZeonQueryVariantTest(unittest.IsolatedAsyncioTestCase):
    def test_model_code_is_prioritized_and_specs_are_ignored(self) -> None:
        variants = ZeonSource._query_variants(
            'Xiaomi TV A Pro 50" 2026 L50MB-APRU '
            '5G 120Hz 33W 8GB/256GB'
        )

        self.assertEqual(variants[0], ("L50MB-APRU", True))
        identifier_values = {
            value.casefold()
            for value, is_identifier in variants
            if is_identifier
        }
        self.assertNotIn("5g", identifier_values)
        self.assertNotIn("120hz", identifier_values)
        self.assertNotIn("33w", identifier_values)
        self.assertNotIn("8gb/256gb", identifier_values)
        self.assertIn(
            ('Xiaomi TV A Pro 50" 2026 L50MB-APRU 5G 120Hz 33W 8GB/256GB', False),
            variants,
        )
        self.assertIn(
            ("Xiaomi TV A Pro 50 2026 L50MB-APRU 5G 120Hz 33W 8GB/256GB", False),
            variants,
        )

    def test_internal_category_redirect_is_safe(self) -> None:
        source = ZeonSource()
        self.assertTrue(
            source._is_safe_page_url(
                "https://www.zeon.by/elektronika/televidenie_i_video/televizory/"
            )
        )
        self.assertFalse(
            source._is_safe_page_url(
                "https://example.com/elektronika/televizory/"
            )
        )
        self.assertFalse(
            source._is_safe_page_url(
                "http://www.zeon.by/elektronika/televizory/"
            )
        )

    async def test_exact_model_code_redirect_has_priority(self) -> None:
        source = ZeonSource()

        async def download(query: str) -> tuple[str, str]:
            if query == "L50MB-APRU":
                return product_page(), PRODUCT_URL
            return (
                search_card(
                    "Телевизор Blackton BT 24F34B",
                    "1669387-blackton-bt-24f34b",
                    "251,30",
                ),
                "https://www.zeon.by/elektronika/televidenie_i_video/televizory/",
            )

        source._download_search_page = AsyncMock(side_effect=download)

        offers = await source.find_offers(CANONICAL_TITLE, limit=20)

        self.assertEqual([item.title for item in offers], [ZEON_TITLE])
        self.assertEqual(offers[0].url, PRODUCT_URL)
        source._download_search_page.assert_awaited_once_with("L50MB-APRU")

    async def test_original_query_remains_fallback(self) -> None:
        source = ZeonSource()

        async def download(query: str) -> tuple[str, str]:
            if query == "HBA534EB3":
                return "<html></html>", "https://www.zeon.by/search/?q=HBA534EB3"
            return (
                search_card(
                    "Электрический духовой шкаф Bosch Serie 4 HBA534EB3",
                    "1779258-bosch-hba534eb3",
                    "1197,70",
                ),
                "https://www.zeon.by/search/?q=Bosch+HBA534EB3",
            )

        source._download_search_page = AsyncMock(side_effect=download)
        offers = await source.find_offers("Bosch HBA534EB3", limit=20)

        self.assertEqual(len(offers), 1)
        self.assertIn("HBA534EB3", offers[0].title)
        self.assertEqual(
            [call.args[0] for call in source._download_search_page.await_args_list],
            ["HBA534EB3", "Bosch HBA534EB3"],
        )


class ZeonAggregateRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def test_xiaomi_tv_is_found_through_model_code_fallback(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=Mock(
                total_offers=2,
                created_products=0,
                merged_offers=0,
                updated_offers=0,
                product_keys=(),
            )
        )
        service = CatalogFirstPriceService(
            catalog_service=catalog_service,
            catalog_search_enabled=False,
            catalog_presentation_enabled=False,
        )
        source = ZeonSource()
        source._download_search_page = AsyncMock(
            return_value=(product_page(), PRODUCT_URL)
        )
        service._zeon_source = source
        service._onliner_queries["l50mbapru"] = "xiaomi tv a pro 50"
        service.search_onliner_key = AsyncMock(
            return_value=[offer("Onliner", CANONICAL_TITLE, 1120.0)]
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=([], False, [])
        )
        service._search_twenty_one_vek_by_query = AsyncMock(return_value=[])
        service._search_shop_by_query = AsyncMock(return_value=[])
        service._search_electrosila_query = AsyncMock(return_value=[])

        result = await service.search_all_sources_by_onliner_key("l50mbapru")

        self.assertEqual(
            [(item.source, item.title) for item in result.offers],
            [("Zeon", ZEON_TITLE), ("Onliner", CANONICAL_TITLE)],
        )
        zeon_status = next(
            item for item in result.source_statuses if item.source == "Zeon"
        )
        self.assertEqual(zeon_status.state, "found")
        self.assertEqual(zeon_status.matched_offers, 1)
        decision = next(
            item for item in result.match_decisions if item.source == "Zeon"
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "exact_match")
        source._download_search_page.assert_awaited_once_with("L50MB-APRU")


if __name__ == "__main__":
    unittest.main()
