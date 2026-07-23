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


class VariantMatchingProductionTest(unittest.IsolatedAsyncioTestCase):
    def test_production_matcher_accepts_compatible_store_wording(self) -> None:
        cases = [
            (
                "Apple iPhone 17 Pro 256GB EU Dual SIM",
                "Смартфон Apple iPhone 17 Pro 12GB/256GB Dual SIM",
            ),
            (
                "Microsoft Xbox Series X 1TB",
                "Игровая приставка Microsoft Xbox Series X 1024GB",
            ),
            (
                "Samsung Galaxy Tab S10 256GB",
                "Samsung Galaxy Tab S10 256GB 5G Global",
            ),
            (
                "Apple iPhone 17 Pro 256GB",
                "Apple iPhone 17 Pro 256GB Dual eSIM",
            ),
        ]
        for canonical, candidate in cases:
            with self.subTest(canonical=canonical, candidate=candidate):
                self.assertIsNone(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    )
                )

    def test_production_matcher_rejects_material_variant_differences(self) -> None:
        cases = [
            (
                "Apple iPhone 17 Pro 256GB",
                "Apple iPhone 17 Pro 512GB",
                "memory",
            ),
            (
                "Apple iPhone 17 Pro 256GB EU",
                "Apple iPhone 17 Pro 256GB US",
                "region",
            ),
            (
                "Apple iPhone 17 Pro 256GB Dual SIM",
                "Apple iPhone 17 Pro 256GB eSIM only",
                "sim",
            ),
            (
                "Samsung Galaxy Tab S10 256GB 4G",
                "Samsung Galaxy Tab S10 256GB 5G",
                "configuration",
            ),
            (
                "Sony PlayStation 5 Slim Digital Edition",
                "Sony PlayStation 5 Slim с дисководом",
                "configuration",
            ),
            (
                "Apple AirPods Pro 2 Lightning",
                "Apple AirPods Pro 2 USB Type-C",
                "configuration",
            ),
            (
                "Roborock Q8 Max с русской озвучкой",
                "Roborock Q8 Max с английской озвучкой",
                "configuration",
            ),
            (
                "Apple iPhone 17 Pro 256GB",
                "Apple iPhone 17 Pro 256GB Open Box",
                "condition",
            ),
            (
                "Sony PlayStation 5 Slim + DualSense",
                "Sony PlayStation 5 Slim + Headset",
                "bundle",
            ),
        ]
        for canonical, candidate, expected in cases:
            with self.subTest(canonical=canonical, candidate=candidate):
                self.assertEqual(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    ),
                    expected,
                )

    async def test_wrong_sim_offer_is_filtered_from_aggregate_result(self) -> None:
        service = CatalogFirstPriceService(catalog_search_enabled=False)
        product_key = "iphone-17-pro-eu-dual-sim"
        canonical = ProductCandidate(
            key=product_key,
            title="Apple iPhone 17 Pro 256GB EU Dual SIM",
            url="https://example.com/iphone-17-pro",
        )
        service._onliner_candidates[product_key] = canonical
        service._onliner_queries[product_key] = canonical.title

        selected = offer("Onliner", canonical.title, 4299)
        wrong_sim = offer(
            "21vek",
            "Apple iPhone 17 Pro 256GB EU eSIM only",
            3599,
        )

        service.search_onliner_key = AsyncMock(return_value=[selected])
        service._search_five_element_by_query = AsyncMock(
            return_value=([], False, [])
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[wrong_sim]
        )
        service._search_shop_by_query = AsyncMock(return_value=[])
        service._search_electrosila_query = AsyncMock(return_value=[])
        service._search_zeon_query = AsyncMock(return_value=[])

        result = await service.search_all_sources_by_onliner_key(
            product_key,
            original_query=canonical.title,
        )

        self.assertEqual([item.price for item in result.offers], [4299])
        status = next(
            item for item in result.source_statuses if item.source == "21vek"
        )
        self.assertEqual(status.state, "filtered")
        self.assertEqual(status.checked_candidates, 1)
        self.assertEqual(status.matched_offers, 0)
        self.assertTrue(
            any(
                decision.source == "21vek"
                and decision.title == wrong_sim.title
                and not decision.accepted
                and decision.reason == "sim"
                for decision in result.match_decisions
            )
        )


if __name__ == "__main__":
    unittest.main()
