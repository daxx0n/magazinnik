import unittest

from app.models.product import ProductCandidate
from app.services.model_selection import (
    group_model_variants,
    requested_color_key,
    selected_color_label,
)


class ContextualColorGroupingTest(unittest.TestCase):
    def candidate(self, key: str, title: str) -> ProductCandidate:
        return ProductCandidate(
            key=key,
            title=title,
            url=f"https://example.com/{key}",
        )

    def test_groups_pixel_official_colors_under_one_model(self) -> None:
        products = [
            self.candidate("base", "Google Pixel 10 Pro XL"),
            self.candidate("jade", "Google Pixel 10 Pro XL (нефрит)"),
            self.candidate("moon", "Google Pixel 10 Pro XL (лунный камень)"),
        ]

        groups = group_model_variants(products)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].title, "Google Pixel 10 Pro XL")
        self.assertEqual(len(groups[0].products), 3)

    def test_groups_colors_before_memory_selection(self) -> None:
        products = [
            self.candidate("a", "Google Pixel 10a 128GB (ягода)"),
            self.candidate("b", "Google Pixel 10a 128GB (туман)"),
            self.candidate("c", "Google Pixel 10a 256GB (лаванда)"),
        ]

        groups = group_model_variants(products)

        self.assertEqual([group.title for group in groups], ["Google Pixel 10a"])
        self.assertEqual(len(groups[0].products), 3)

    def test_recognizes_exact_pixel_color_names(self) -> None:
        expected = {
            "нефрит": "jade",
            "лунный камень": "moonstone",
            "туман": "mist",
            "лаванда": "lavender",
            "фрост": "frost",
            "лемонграсс": "lemongrass",
            "индиго": "indigo",
            "лесной орех": "hazel",
            "ягода": "berry",
        }
        for label, key in expected.items():
            with self.subTest(label=label):
                title = f"Google Pixel 10 ({label})"
                self.assertEqual(requested_color_key(title), key)
                self.assertIsNotNone(selected_color_label(title))

    def test_does_not_collapse_technical_parentheses(self) -> None:
        products = [
            self.candidate("wifi", "Tablet X (Wi-Fi)"),
            self.candidate("lte", "Tablet X (LTE)"),
            self.candidate("global", "Phone Y (Global)"),
            self.candidate("china", "Phone Y (China)"),
        ]

        groups = group_model_variants(products)

        self.assertEqual(len(groups), 4)
        self.assertEqual(
            {group.title for group in groups},
            {
                "Tablet X (Wi-Fi)",
                "Tablet X (LTE)",
                "Phone Y (Global)",
                "Phone Y (China)",
            },
        )

    def test_contextually_groups_unknown_color_like_suffixes(self) -> None:
        products = [
            self.candidate("base", "Acme Phone 12 256GB"),
            self.candidate("one", "Acme Phone 12 256GB (Aurora Mist)"),
            self.candidate("two", "Acme Phone 12 256GB (Forest Pearl)"),
        ]

        groups = group_model_variants(products)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].title, "Acme Phone 12")


if __name__ == "__main__":
    unittest.main()
