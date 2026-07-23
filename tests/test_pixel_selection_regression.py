import unittest
from unittest.mock import AsyncMock, Mock

from app.models.product import ProductCandidate
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_selection import (
    filter_products_by_query_generation,
    group_model_variants,
    model_variant_title,
    requested_color_key,
    selected_color_label,
    significant_model_numbers,
)


def product(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(
        key=key,
        title=title,
        url=f"https://example.com/{key}",
    )


class PixelSelectionRegressionTest(unittest.IsolatedAsyncioTestCase):
    def test_pixel_color_buttons_keep_mint_hazel_and_obsidian_separate(self) -> None:
        titles = [
            "Google Pixel 8 8GB/256GB (мятный зеленый)",
            "Google Pixel 8 8GB/256GB (лесной орех)",
            "Google Pixel 8 8GB/256GB (Obsidian)",
        ]

        keys = [requested_color_key(title) for title in titles]

        self.assertEqual(keys, ["mint", "hazel", "obsidian"])
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(selected_color_label(titles[1]), "Лесной орех")

    def test_exact_color_still_accepts_generic_same_family_fallback(self) -> None:
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                "Google Pixel 8 8GB/256GB Mint",
                "Google Pixel 8 8GB/256GB Green",
                requested_title="Google Pixel 8 8GB/256GB Mint",
            )
        )
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                "Google Pixel 8 8GB/256GB Mint",
                "Google Pixel 8 8GB/256GB Hazel",
                requested_title="Google Pixel 8 8GB/256GB Mint",
            ),
            "color",
        )

    def test_isai_blue_is_a_color_not_a_separate_model(self) -> None:
        products = [
            product("pixel10a", "Google Pixel 10a"),
            product("pixel10a-isai", "Google Pixel 10a Isai Blue"),
        ]

        groups = group_model_variants(products)

        self.assertEqual(model_variant_title(products[1].title), "Google Pixel 10a")
        self.assertEqual(selected_color_label(products[1].title), "Isai Blue")
        self.assertEqual([group.title for group in groups], ["Google Pixel 10a"])
        self.assertEqual(len(groups[0].products), 2)

    def test_generation_parser_understands_letter_suffix_models(self) -> None:
        self.assertEqual(significant_model_numbers("Google Pixel 10a"), {"10"})
        self.assertEqual(significant_model_numbers("Google Pixel 8a"), {"8"})
        self.assertEqual(
            significant_model_numbers("Google Pixel 8 8GB/256GB"),
            {"8"},
        )

    def test_pixel_8_query_filters_other_generations(self) -> None:
        products = [
            product("pixel10a", "Google Pixel 10a Isai Blue"),
            product("pixel9a", "Google Pixel 9a"),
            product("pixel8jp", "Google Pixel 8 японская версия"),
            product("pixel8pro", "Google Pixel 8 Pro"),
            product("pixel8a", "Google Pixel 8a"),
            product("pixel8", "Google Pixel 8"),
            product("pixel7a", "Google Pixel 7a"),
            product("pixel7", "Google Pixel 7"),
        ]

        filtered = filter_products_by_query_generation(products, "pixel 8")

        self.assertEqual(
            [item.key for item in filtered],
            ["pixel8jp", "pixel8pro", "pixel8a", "pixel8"],
        )

    async def test_live_discovery_applies_generation_filter(self) -> None:
        service = CatalogFirstPriceService(
            catalog_service=Mock(),
            catalog_search_enabled=False,
        )
        service._onliner_source.find_products = AsyncMock(
            return_value=[
                product("pixel10a", "Google Pixel 10a Isai Blue"),
                product("pixel9a", "Google Pixel 9a"),
                product("pixel8a", "Google Pixel 8a"),
                product("pixel8", "Google Pixel 8"),
                product("pixel7", "Google Pixel 7"),
            ]
        )

        results = await service.find_onliner_products("pixel 8")

        self.assertEqual([item.key for item in results], ["pixel8a", "pixel8"])

    def test_generation_filter_falls_back_when_no_exact_result_exists(self) -> None:
        products = [
            product("pixel9", "Google Pixel 9"),
            product("pixel7", "Google Pixel 7"),
        ]

        self.assertEqual(
            filter_products_by_query_generation(products, "pixel 8"),
            products,
        )


if __name__ == "__main__":
    unittest.main()
