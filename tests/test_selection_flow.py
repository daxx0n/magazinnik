import unittest

from app.models.product import ProductCandidate
from app.services.model_selection import group_model_variants
from app.services.selection_flow import (
    ordered_memory_groups,
    ordered_variant_groups,
)


def product(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(key=key, title=title, url=f"https://example.com/{key}")


class SelectionFlowTest(unittest.TestCase):
    def test_devices_are_sorted_from_greater_to_smaller(self) -> None:
        products = [
            product("iphone15", "Apple iPhone 15 128GB Black"),
            product("iphone17", "Apple iPhone 17 128GB Black"),
            product("iphone16", "Apple iPhone 16 128GB Black"),
        ]

        groups = ordered_variant_groups(products, group_model_variants)

        self.assertEqual(
            [group.title for group in groups],
            ["Apple iPhone 17", "Apple iPhone 16", "Apple iPhone 15"],
        )

    def test_memory_is_sorted_from_greater_to_smaller(self) -> None:
        products = [
            product("128", "Apple iPhone 17 128GB Black"),
            product("1tb", "Apple iPhone 17 1TB Black"),
            product("256", "Apple iPhone 17 256GB Black"),
            product("512", "Apple iPhone 17 512GB Black"),
        ]

        groups = ordered_memory_groups(products)

        self.assertEqual(
            [label for label, _ in groups],
            ["1TB", "512GB", "256GB", "128GB"],
        )

    def test_ram_storage_pairs_are_sorted_by_larger_configuration(self) -> None:
        products = [
            product("8-128", "Google Pixel 8 8GB/128GB Black"),
            product("12-256", "Google Pixel 8 12GB/256GB Black"),
            product("8-256", "Google Pixel 8 8GB/256GB Black"),
        ]

        groups = ordered_memory_groups(products)

        self.assertEqual(
            [label for label, _ in groups],
            ["12GB/256GB", "8GB/256GB", "8GB/128GB"],
        )


if __name__ == "__main__":
    unittest.main()
