import unittest

from app.models.product import ProductCandidate
from app.services.product_variants import (
    base_product_title,
    extract_color,
    extract_color_key,
    extract_memory,
    group_by_memory,
    group_product_variants,
)


def candidate(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(
        key=key,
        title=title,
        url=f"https://example.com/{key}",
    )


class ProductVariantsTest(unittest.TestCase):
    def test_extracts_common_memory_formats(self) -> None:
        cases = [
            ("Apple iPhone 17 256GB", "256GB"),
            ("Samsung A55 8GB/256GB", "8GB/256GB"),
            ("Ноутбук 16/512 Midnight", "16/512"),
        ]

        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_memory(title),
                    expected,
                )

    def test_extracts_color_without_other_parentheses(self) -> None:
        self.assertEqual(
            extract_color("Apple iPhone 17 (черный)"),
            "черный",
        )
        self.assertIsNone(
            extract_color(
                "Apple AirPods Pro 2 (с разъемом USB-C)"
            )
        )
        self.assertEqual(
            extract_color_key(
                "Apple iPhone 17 512GB Black"
            ),
            "black",
        )
        self.assertEqual(
            extract_color_key(
                "Apple iPhone 17 512GB (черный)"
            ),
            "black",
        )

    def test_groups_model_memory_and_colors(self) -> None:
        products = [
            candidate(
                "128black",
                "Apple iPhone 17 128GB (черный)",
            ),
            candidate(
                "256black",
                "Apple iPhone 17 256GB (черный)",
            ),
            candidate(
                "256white",
                "Apple iPhone 17 256GB (белый)",
            ),
            candidate(
                "pro",
                "Apple iPhone 17 Pro 256GB (черный)",
            ),
        ]

        groups = group_product_variants(products)

        self.assertEqual(
            [group.title for group in groups],
            ["Apple iPhone 17", "Apple iPhone 17 Pro"],
        )
        self.assertEqual(
            [
                label
                for label, _ in group_by_memory(
                    groups[0].products
                )
            ],
            ["128GB", "256GB"],
        )
        self.assertEqual(
            base_product_title(
                "Samsung Galaxy A55 8GB/256GB (лиловый)"
            ),
            "Samsung Galaxy A55",
        )


if __name__ == "__main__":
    unittest.main()
