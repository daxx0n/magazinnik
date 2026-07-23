import unittest

from app.models.product import ProductCandidate
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_selection import (
    group_model_variants,
    model_variant_title,
    selected_color_label,
)


def candidate(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(
        key=key,
        title=title,
        url=f"https://example.com/{key}",
    )


class GenericVariantMatchingTest(unittest.TestCase):
    def test_groups_colors_for_multiple_brands_and_categories(self) -> None:
        cases = [
            (
                [
                    candidate(
                        "iphone-natural",
                        "Apple iPhone 15 Pro 256GB Natural Titanium",
                    ),
                    candidate(
                        "iphone-blue",
                        "Apple iPhone 15 Pro 256GB Blue Titanium",
                    ),
                ],
                "Apple iPhone 15 Pro",
            ),
            (
                [
                    candidate(
                        "samsung-navy",
                        "Samsung Galaxy S25 12GB/256GB Navy",
                    ),
                    candidate(
                        "samsung-mint",
                        "Samsung Galaxy S25 12GB/256GB Mint",
                    ),
                ],
                "Samsung Galaxy S25",
            ),
            (
                [
                    candidate(
                        "lenovo-gray",
                        "Lenovo Legion 5 16GB/512GB Storm Grey",
                    ),
                    candidate(
                        "lenovo-white",
                        "Lenovo Legion 5 16GB/512GB Glacier White",
                    ),
                ],
                "Lenovo Legion 5",
            ),
            (
                [
                    candidate("bosch-black", "Bosch HBA534EB3 Black"),
                    candidate("bosch-white", "Bosch HBA534EB3 White"),
                ],
                "Bosch HBA534EB3",
            ),
        ]

        for products, expected_title in cases:
            with self.subTest(expected_title=expected_title):
                groups = group_model_variants(products)
                self.assertEqual(len(groups), 1)
                self.assertEqual(groups[0].title, expected_title)
                self.assertEqual(len(groups[0].products), 2)

    def test_internal_color_word_remains_part_of_model(self) -> None:
        self.assertEqual(
            model_variant_title(
                "Black Shark 5 Pro 12GB/256GB Black"
            ),
            "Black Shark 5 Pro",
        )
        self.assertEqual(
            model_variant_title("Black Shark 5 Pro 12GB/256GB"),
            "Black Shark 5 Pro",
        )

    def test_displays_generic_marketing_color_suffixes(self) -> None:
        cases = {
            "Apple iPhone 15 Pro Natural Titanium": "Natural Titanium",
            "Samsung Galaxy S25 Navy": "Navy",
            "Lenovo Legion 5 Storm Grey": "Storm Grey",
            "Консоль PlayStation 5 Slim белый": "Белый",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(selected_color_label(title), expected)

    def test_rejects_other_generation_before_color(self) -> None:
        reason = CatalogFirstPriceService._model_mismatch_reason(
            "Google Pixel 8 8GB/128GB Mint",
            "Google Pixel 7 8GB/128GB Hazel",
            requested_title="Google Pixel 8 8GB/128GB Mint",
        )
        self.assertEqual(reason, "model_number")

    def test_rejects_exact_marketing_variant_differences(self) -> None:
        cases = [
            (
                "Google Pixel 8 8GB/128GB Mint",
                "Google Pixel 8 8GB/128GB Hazel",
            ),
            (
                "Google Pixel 10 12GB/256GB Jade",
                "Google Pixel 10 12GB/256GB Moonstone",
            ),
            (
                "Apple iPhone 15 Pro 256GB Natural Titanium",
                "Apple iPhone 15 Pro 256GB Blue Titanium",
            ),
            (
                "Samsung Galaxy S24 Ultra Titanium Gray",
                "Samsung Galaxy S24 Ultra Titanium Black",
            ),
            (
                "Xiaomi 15 Forest Green",
                "Xiaomi 15 Ocean Blue",
            ),
        ]
        for canonical, other in cases:
            with self.subTest(canonical=canonical):
                self.assertEqual(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        other,
                        requested_title=canonical,
                    ),
                    "color",
                )

    def test_accepts_confirmed_aliases_and_base_color_fallback(self) -> None:
        cases = [
            (
                "Google Pixel 8 8GB/128GB Obsidian",
                "Телефон Google Pixel 8 8/128 ГБ обсидиан",
            ),
            (
                "Google Pixel 8 8GB/128GB Obsidian",
                "Телефон Google Pixel 8 8/128 ГБ черный",
            ),
            (
                "Samsung Galaxy S25 12GB/256GB Navy",
                "Смартфон Samsung Galaxy S25 12/256GB темно-синий",
            ),
            (
                "Apple iPhone 15 Pro 256GB Natural Titanium",
                "Смартфон Apple iPhone 15 Pro 256 ГБ природный титан",
            ),
        ]
        for canonical, candidate_title in cases:
            with self.subTest(canonical=canonical):
                self.assertIsNone(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate_title,
                        requested_title=canonical,
                    )
                )


if __name__ == "__main__":
    unittest.main()
