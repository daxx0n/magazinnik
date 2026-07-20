import unittest
from unittest.mock import AsyncMock, Mock

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_selection import (
    collapse_color_variants,
    group_model_variants,
    model_variant_title,
    selected_color_label,
    significant_model_numbers,
)


def offer(source: str, title: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{source.casefold()}",
    )


class ModelSelectionTest(unittest.IsolatedAsyncioTestCase):
    def test_memory_does_not_mask_pixel_generation(self) -> None:
        self.assertEqual(
            significant_model_numbers(
                "Телефон Google Pixel 7 8GB/128GB (снег)"
            ),
            {"7"},
        )
        reason = CatalogFirstPriceService._model_mismatch_reason(
            canonical_title=(
                "Google Pixel 8 8GB/128GB (мятный зеленый)"
            ),
            candidate_title=(
                "Телефон Google Pixel 7 8GB/128GB (снег)"
            ),
            requested_title="Google Pixel 8",
        )
        self.assertEqual(reason, "model_number")

    def test_selected_variant_rejects_different_color(self) -> None:
        reason = CatalogFirstPriceService._model_mismatch_reason(
            canonical_title="Google Pixel 8 8GB/128GB (мятный зеленый)",
            candidate_title="Google Pixel 8 8GB/128GB (белый)",
            requested_title="Google Pixel 8 8GB/128GB (мятный зеленый)",
        )
        self.assertEqual(reason, "color")

    def test_selected_variant_rejects_unknown_color(self) -> None:
        reason = CatalogFirstPriceService._model_mismatch_reason(
            canonical_title="Google Pixel 8 8GB/128GB (Obsidian)",
            candidate_title="Google Pixel 8 8GB/128GB",
            requested_title="Google Pixel 8 8GB/128GB (Obsidian)",
        )
        self.assertEqual(reason, "color_unknown")

    def test_russian_obsidian_is_grouped_inside_pixel_8_model(self) -> None:
        products = [
            ProductCandidate(
                key="pixel8-default",
                title="Google Pixel 8 8GB/128GB",
                url="https://example.com/pixel8-default",
            ),
            ProductCandidate(
                key="pixel8-obsidian",
                title="Google Pixel 8 8GB/128GB (обсидиан)",
                url="https://example.com/pixel8-obsidian",
            ),
            ProductCandidate(
                key="pixel7",
                title="Google Pixel 7 8GB/128GB (снег)",
                url="https://example.com/pixel7",
            ),
        ]

        groups = group_model_variants(products)

        self.assertEqual(
            [group.title for group in groups],
            ["Google Pixel 8", "Google Pixel 7"],
        )
        self.assertEqual(len(groups[0].products), 2)
        self.assertEqual(
            model_variant_title("Google Pixel 8 8GB/128GB (обсидиан)"),
            "Google Pixel 8",
        )
        self.assertEqual(
            selected_color_label(
                "Google Pixel 8 8GB/128GB (обсидиан)"
            ),
            "Обсидиан",
        )

    def test_color_collapse_preserves_memory_and_pro_variants(self) -> None:
        products = [
            ProductCandidate(
                key="pixel8-mint",
                title="Google Pixel 8 8GB/128GB (мятный зеленый)",
                url="https://example.com/pixel8-mint",
            ),
            ProductCandidate(
                key="pixel8-snow",
                title="Google Pixel 8 8GB/128GB (снег)",
                url="https://example.com/pixel8-snow",
            ),
            ProductCandidate(
                key="pixel8-256",
                title="Google Pixel 8 8GB/256GB (obsidian)",
                url="https://example.com/pixel8-256",
            ),
            ProductCandidate(
                key="pixel8-pro",
                title="Google Pixel 8 Pro 12GB/128GB (obsidian)",
                url="https://example.com/pixel8-pro",
            ),
            ProductCandidate(
                key="pixel7",
                title="Google Pixel 7 8GB/128GB (snow)",
                url="https://example.com/pixel7",
            ),
        ]

        collapsed = collapse_color_variants(products, "Google Pixel")

        self.assertEqual(
            [product.key for product in collapsed],
            ["pixel8-mint", "pixel8-256", "pixel8-pro", "pixel7"],
        )

    def test_explicit_color_does_not_collapse_choices(self) -> None:
        products = [
            ProductCandidate(
                key="mint",
                title="Google Pixel 8 8GB/128GB (mint)",
                url="https://example.com/mint",
            ),
            ProductCandidate(
                key="snow",
                title="Google Pixel 8 8GB/128GB (snow)",
                url="https://example.com/snow",
            ),
        ]
        self.assertEqual(
            collapse_color_variants(products, "Google Pixel 8 mint"),
            products,
        )

    async def test_live_search_preserves_color_candidates_for_ui(self) -> None:
        service = CatalogFirstPriceService(
            catalog_service=Mock(),
            catalog_search_enabled=False,
        )
        service._onliner_source.find_products = AsyncMock(
            return_value=[
                ProductCandidate(
                    key="mint",
                    title="Google Pixel 8 8GB/128GB (mint)",
                    url="https://example.com/mint",
                ),
                ProductCandidate(
                    key="snow",
                    title="Google Pixel 8 8GB/128GB (snow)",
                    url="https://example.com/snow",
                ),
                ProductCandidate(
                    key="pixel7",
                    title="Google Pixel 7 8GB/128GB (snow)",
                    url="https://example.com/pixel7",
                ),
            ]
        )

        products = await service.find_onliner_products("Google Pixel")

        self.assertEqual(
            [product.key for product in products],
            ["mint", "snow", "pixel7"],
        )

    async def test_broad_query_still_rejects_pixel_6_after_pixel_8_selection(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=Mock(
                total_offers=1,
                created_products=1,
                merged_offers=0,
                updated_offers=0,
                product_keys=("product-1",),
            )
        )
        service = CatalogFirstPriceService(
            catalog_service=catalog_service,
            catalog_search_enabled=False,
            catalog_presentation_enabled=False,
        )
        service._onliner_queries["pixel8"] = "Pixel"
        service.search_onliner_key = AsyncMock(
            return_value=[
                offer(
                    "Onliner",
                    "Google Pixel 8 8GB/128GB (мятный зеленый)",
                    2099.0,
                )
            ]
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=([], False, [])
        )
        service._search_twenty_one_vek_by_query = AsyncMock(return_value=[])
        service._search_shop_by_query = AsyncMock(
            return_value=[
                offer(
                    "Shop.by",
                    "Телефон Google Pixel 6 8GB/128GB (Black)",
                    900.0,
                )
            ]
        )
        service._search_electrosila_query = AsyncMock(return_value=[])
        service._search_zeon_query = AsyncMock(return_value=[])

        result = await service.search_all_sources_by_onliner_key("pixel8")

        self.assertEqual([item.source for item in result.offers], ["Onliner"])
        shop_status = next(
            status
            for status in result.source_statuses
            if status.source == "Shop.by"
        )
        self.assertEqual(shop_status.state, "filtered")
        shop_decision = next(
            decision
            for decision in result.match_decisions
            if decision.source == "Shop.by"
        )
        self.assertFalse(shop_decision.accepted)
        self.assertEqual(shop_decision.reason, "model_number")


if __name__ == "__main__":
    unittest.main()
