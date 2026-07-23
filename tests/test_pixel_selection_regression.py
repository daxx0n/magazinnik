import unittest
from unittest.mock import AsyncMock, Mock

from app.models.product import ProductCandidate
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_selection import filter_products_by_query_generation
from app.services.selection_presentation import (
    group_selection_model_variants,
    selection_color_key,
    selection_color_label,
)


def product(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(
        key=key,
        title=title,
        url=f"https://example.com/{key}",
    )


class PixelSelectionRegressionTest(unittest.IsolatedAsyncioTestCase):
    def test_pixel_color_keyboard_keeps_three_exact_colors(self) -> None:
        titles = [
            "Google Pixel 8 8GB/256GB (мятный зеленый)",
            "Google Pixel 8 8GB/256GB (лесной орех)",
            "Google Pixel 8 8GB/256GB (Obsidian)",
        ]

        keys = [selection_color_key(title) for title in titles]

        self.assertEqual(keys, ["mint", "hazel", "obsidian"])
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(selection_color_label(titles[1]), "Лесной орех")

    def test_isai_blue_is_grouped_as_color_not_model_name(self) -> None:
        products = [
            product("pixel10a", "Google Pixel 10a"),
            product("pixel10a-isai", "Google Pixel 10a Isai Blue"),
        ]

        groups = group_selection_model_variants(products)

        self.assertEqual([group.title for group in groups], ["Google Pixel 10a"])
        self.assertEqual(len(groups[0].products), 2)
        self.assertEqual(
            groups[0].products[1].title,
            "Google Pixel 10a Isai Blue",
        )
        self.assertEqual(
            selection_color_key(groups[0].products[1].title),
            "isai_blue",
        )
        self.assertEqual(
            selection_color_label(groups[0].products[1].title),
            "Isai Blue",
        )

    def test_pixel_8_query_filters_neighboring_generations(self) -> None:
        products = [
            product("pixel10a", "Google Pixel 10a Isai Blue"),
            product("pixel9a", "Google Pixel 9a"),
            product("pixel8jp", "Google Pixel 8 японская версия"),
            product("pixel8pro", "Google Pixel 8 Pro"),
            product("pixel8a", "Google Pixel 8a"),
            product("pixel8", "Google Pixel 8"),
            product("pixel7a", "Google Pixel 7a японская версия"),
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

    def test_generation_filter_falls_back_when_no_match_exists(self) -> None:
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
