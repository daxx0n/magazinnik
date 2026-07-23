import unittest
from unittest.mock import AsyncMock

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.catalog_first_search import CatalogFirstPriceService


def offer(source: str, title: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{source.casefold()}/{price}",
    )


class ColorMatchingProductionTest(unittest.IsolatedAsyncioTestCase):
    def test_brand_color_matrix_uses_production_matcher(self) -> None:
        accepted = [
            (
                "Google Pixel 8 8GB/128GB (Mint)",
                "Google Pixel 8 8GB/128GB (мятный зеленый)",
            ),
            (
                "Google Pixel 8 8GB/128GB (Hazel)",
                "Google Pixel 8 8GB/128GB (лесной орех)",
            ),
            (
                "Apple iPhone 15 Pro 256GB Natural Titanium",
                "Apple iPhone 15 Pro 256GB натуральный титан",
            ),
            (
                "Samsung Galaxy S24 Ultra Titanium Gray",
                "Samsung Galaxy S24 Ultra титановый серый",
            ),
            (
                "Xiaomi 15 Ocean Blue",
                "Xiaomi 15 океанский синий",
            ),
            (
                "Xiaomi 15 Forest Green",
                "Xiaomi 15 лесной зеленый",
            ),
        ]
        rejected = [
            (
                "Google Pixel 8 8GB/128GB (Mint)",
                "Google Pixel 8 8GB/128GB (Hazel)",
            ),
            (
                "Google Pixel 8 8GB/128GB (Mint)",
                "Google Pixel 8 8GB/128GB (лесной орех)",
            ),
            (
                "Google Pixel 8 8GB/128GB (Mint)",
                "Google Pixel 8 8GB/128GB (Obsidian)",
            ),
            (
                "Google Pixel 10 12GB/256GB Jade",
                "Google Pixel 10 12GB/256GB Moonstone",
            ),
            (
                "Apple iPhone 15 Pro Natural Titanium",
                "Apple iPhone 15 Pro Blue Titanium",
            ),
            (
                "Apple iPhone 15 Pro Black Titanium",
                "Apple iPhone 15 Pro White Titanium",
            ),
            (
                "Samsung Galaxy S24 Ultra Titanium Gray",
                "Samsung Galaxy S24 Ultra Titanium Black",
            ),
            (
                "Samsung Galaxy S25 Mint",
                "Samsung Galaxy S25 Jade Green",
            ),
            (
                "Xiaomi 15 Midnight Black",
                "Xiaomi 15 Aurora Glow",
            ),
        ]

        for canonical, candidate in accepted:
            with self.subTest(kind="accepted", canonical=canonical):
                self.assertIsNone(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    )
                )
        for canonical, candidate in rejected:
            with self.subTest(kind="rejected", canonical=canonical):
                self.assertEqual(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    ),
                    "color",
                )

    def test_no_selected_color_does_not_filter_candidates(self) -> None:
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                "Black Shark 5 Pro 12GB/256GB",
                "Black Shark 5 Pro 12GB/256GB Red",
                requested_title="Black Shark 5 Pro 12GB/256GB",
            )
        )

    async def test_pixel_mint_hazel_regression_filters_cheapest_wrong_offer(self):
        service = CatalogFirstPriceService(catalog_search_enabled=False)
        product_key = "pixel-8-mint"
        canonical = ProductCandidate(
            key=product_key,
            title="Google Pixel 8 8GB/128GB (мятный зеленый)",
            url="https://example.com/pixel-8-mint",
        )
        service._onliner_candidates[product_key] = canonical
        service._onliner_queries[product_key] = "Google Pixel 8 мятный зеленый"

        mint = offer(
            "Onliner",
            "Google Pixel 8 8GB/128GB (мятный зеленый)",
            2099,
        )
        hazel = offer(
            "21vek",
            "Google Pixel 8 8GB/128GB (лесной орех)",
            1080,
        )

        service.search_onliner_key = AsyncMock(return_value=[mint])
        service._search_five_element_by_query = AsyncMock(
            return_value=([], False, [])
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[hazel]
        )
        service._search_shop_by_query = AsyncMock(return_value=[])
        service._search_electrosila_query = AsyncMock(return_value=[])
        service._search_zeon_query = AsyncMock(return_value=[])

        result = await service.search_all_sources_by_onliner_key(
            product_key,
            original_query="Google Pixel 8 мятный зеленый",
        )

        self.assertEqual([item.price for item in result.offers], [2099])
        self.assertEqual(result.offers[0].title, mint.title)
        self.assertNotIn(hazel, result.offers)

        twenty_one_status = next(
            status for status in result.source_statuses
            if status.source == "21vek"
        )
        self.assertEqual(twenty_one_status.state, "filtered")
        self.assertEqual(twenty_one_status.matched_offers, 0)
        self.assertEqual(twenty_one_status.checked_candidates, 1)
        self.assertTrue(
            any(
                decision.source == "21vek"
                and decision.title == hazel.title
                and not decision.accepted
                and decision.reason == "color"
                for decision in result.match_decisions
            )
        )


if __name__ == "__main__":
    unittest.main()
