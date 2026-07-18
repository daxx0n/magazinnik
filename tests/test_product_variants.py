import unittest

from app.models.product import ProductCandidate
from app.services.product_variants import (
    base_product_title,
    display_color,
    display_product_title,
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
    def test_displays_original_marketing_color_names(self) -> None:
        cases = [
            (
                "Apple iPhone 17 512GB (черный)",
                "Black",
            ),
            (
                "Apple iPhone 17 512GB (голубой)",
                "Mist Blue",
            ),
            (
                "Apple iPhone 17 512GB (сиреневый)",
                "Lavender",
            ),
            (
                "Apple iPhone 17 Pro 512GB (оранжевый)",
                "Cosmic Orange",
            ),
            (
                "Apple iPhone 17 Pro 256GB (глубокий синий)",
                "Deep Blue",
            ),
            (
                "Samsung Galaxy S25 (синий)",
                "Blue",
            ),
            (
                "Google Pixel 10 (Obsidian)",
                "Obsidian",
            ),
            (
                "Apple iPhone 15 Pro (природный титан)",
                "Natural Titanium",
            ),
            (
                "Пылесос (матовый черный/медный)",
                "Matte Black/Copper",
            ),
        ]

        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(
                    display_color(title),
                    expected,
                )

        self.assertEqual(
            display_product_title(
                "Apple iPhone 17 512GB (голубой)"
            ),
            "Apple iPhone 17 512GB (Mist Blue)",
        )

    def test_extracts_common_memory_formats(self) -> None:
        cases = [
            ("Apple iPhone 17 256GB", "256GB"),
            ("Samsung A55 8GB/256GB", "8GB/256GB"),
            ("Ноутбук 16/512 Midnight", "16GB/512GB"),
            ("Samsung S25 12/256 ГБ", "12GB/256GB"),
            ("Samsung A55 8/256GB", "8GB/256GB"),
            ("Ноутбук 1TB/16GB", "16GB/1TB"),
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

    def test_color_detection_uses_words_not_brand_substrings(self) -> None:
        cases = [
            (
                "Blackview BV9300 Pro 12GB/256GB (зеленый)",
                "green",
            ),
            (
                "GoldStar LT-55T450 (серебристый)",
                "silver",
            ),
            ("Xiaomi Redmi Note 13 Pro", None),
            ("Xiaomi Redmi Note 13 Pro White", "white"),
        ]

        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(extract_color_key(title), expected)

    def test_keeps_similar_colors_distinct(self) -> None:
        cases = [
            ("Телефон (черный)", "black"),
            ("Телефон (графитовый)", "graphite"),
            ("Телефон (синий)", "blue"),
            ("Телефон (голубой)", "light_blue"),
            ("Телефон (бирюзовый)", "turquoise"),
            ("Телефон (сиреневый)", "lavender"),
            ("Телефон (Lilac)", "lilac"),
            ("Google Pixel (Obsidian)", "black"),
            ("Google Pixel (Porcelain)", "white"),
            (
                "Apple iPhone 17 (синий)",
                "light_blue",
            ),
            (
                "Apple iPhone 17 (фиолетовый)",
                "lavender",
            ),
            (
                "Apple iPhone 17 Pro (темно-синий)",
                "dark_blue",
            ),
            (
                "Apple iPhone 17 Pro (глубокий синий)",
                "dark_blue",
            ),
            (
                "Apple iPhone Air (золотистый)",
                "light_gold",
            ),
        ]

        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(extract_color_key(title), expected)

    def test_does_not_treat_configuration_as_color(self) -> None:
        cases = [
            "Huawei MatePad 11.5 (Wi-Fi)",
            "Samsung Galaxy S25 (Global)",
            "Ноутбук (с клавиатурой)",
            "Телевизор LG OLED55C4RLA (OLED)",
            "Смартфон Samsung Galaxy A55 (NFC)",
            "Смартфон Samsung Galaxy A55 (AMOLED)",
        ]

        for title in cases:
            with self.subTest(title=title):
                self.assertIsNone(extract_color(title))
                self.assertEqual(base_product_title(title), title)
        self.assertEqual(
            extract_color_key(
                "Apple iPhone 17 512GB (черный)"
            ),
            "black",
        )

    def test_keeps_marketing_color_variants_distinct(self) -> None:
        cases = [
            ("Phone (Blue)", "blue"),
            ("Phone (Dark Blue)", "dark_blue"),
            ("Phone (Light Blue)", "light_blue"),
            ("Phone (Natural Titanium)", "natural_titanium"),
            ("Phone (Desert Titanium)", "desert_titanium"),
            ("Phone (Black Titanium)", "black_titanium"),
            ("Phone (Midnight)", "midnight"),
            ("Phone (Starlight)", "starlight"),
            ("Phone (Dark Green)", "dark_green"),
            ("Phone (Light Gold)", "light_gold"),
            ("Phone (Rose Gold)", "rose_gold"),
        ]

        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(extract_color_key(title), expected)

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

    def test_sorts_memory_options_by_capacity(self) -> None:
        products = [
            candidate("1tb", "Phone 1TB (Black)"),
            candidate("256", "Phone 256GB (Black)"),
            candidate("128", "Phone 128GB (Black)"),
            candidate("512", "Phone 512GB (Black)"),
        ]

        self.assertEqual(
            [label for label, _ in group_by_memory(products)],
            ["128GB", "256GB", "512GB", "1TB"],
        )


if __name__ == "__main__":
    unittest.main()
