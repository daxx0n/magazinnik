import inspect
import unittest

from app.handlers import search
from app.models.product import ProductCandidate
from app.services.selection_flow import (
    has_memory_choice,
    selectable_memory_groups,
)


def candidate(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(
        key=key,
        title=title,
        url=f"https://example.com/{key}",
    )


class ConditionalMemorySelectionTest(unittest.TestCase):
    def test_memory_step_is_hidden_for_products_without_memory(self) -> None:
        products = [
            candidate("tv-black", "LG 43NU900B6LA (черный)"),
            candidate("tv-white", "LG 43NU900B6LA (белый)"),
        ]

        self.assertFalse(has_memory_choice(products))
        self.assertEqual(selectable_memory_groups(products), [])

    def test_memory_step_is_hidden_for_single_memory_configuration(self) -> None:
        products = [
            candidate("phone-black", "Google Pixel 8 8GB/256GB (Obsidian)"),
            candidate("phone-mint", "Google Pixel 8 8GB/256GB (Mint)"),
        ]

        self.assertFalse(has_memory_choice(products))
        self.assertEqual(
            [label for label, _ in selectable_memory_groups(products)],
            ["8GB/256GB"],
        )

    def test_memory_step_is_shown_for_multiple_real_configurations(self) -> None:
        products = [
            candidate("phone-128", "Samsung Galaxy A55 8GB/128GB (черный)"),
            candidate("phone-256", "Samsung Galaxy A55 8GB/256GB (черный)"),
            candidate("phone-unknown", "Samsung Galaxy A55 (черный)"),
        ]

        self.assertTrue(has_memory_choice(products))
        self.assertEqual(
            [label for label, _ in selectable_memory_groups(products)],
            ["8GB/256GB", "8GB/128GB"],
        )


class SearchPresentationContractTest(unittest.TestCase):
    def test_offer_output_has_universal_product_icon_and_no_updated_line(self) -> None:
        source = inspect.getsource(search)

        self.assertNotIn("🕒 Обновлено:", source)
        self.assertNotIn("📱 ", source)
        self.assertIn("🏷️ ", source)

    def test_no_memory_flow_supports_direct_all_color_callback(self) -> None:
        group_source = inspect.getsource(search.handle_variant_group)
        any_color_source = inspect.getsource(search.handle_any_color_selection)

        self.assertIn('raw_memory_index}:all', group_source)
        self.assertIn("memory_selected=False", group_source)
        self.assertIn('raw_memory_index == "all"', any_color_source)


if __name__ == "__main__":
    unittest.main()
