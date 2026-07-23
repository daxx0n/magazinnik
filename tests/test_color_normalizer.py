import unittest

from app.services.color_normalizer import (
    BASE_COLOR,
    EXACT_VARIANT,
    colors_match,
    extract_color_identity,
    extract_color_phrase,
    normalize_color,
)


class ColorNormalizerTest(unittest.TestCase):
    def test_pixel_mint_matches_multilingual_aliases(self):
        aliases = [
            "mint",
            "Mint green",
            "мятный",
            "мятный зелёный",
            "зелёный мятный",
            "мятно-зелёный",
        ]
        for alias in aliases:
            with self.subTest(alias=alias):
                identity = normalize_color(alias)
                self.assertIsNotNone(identity)
                self.assertEqual(identity.variant, "mint")
                self.assertEqual(identity.confidence, EXACT_VARIANT)
                self.assertTrue(colors_match("Mint", alias))

    def test_exact_pixel_variants_remain_distinct(self):
        for candidate in ("Hazel", "лесной орех", "Obsidian", "Jade"):
            with self.subTest(candidate=candidate):
                self.assertFalse(colors_match("Mint", candidate))

    def test_hazel_translation_matches_without_global_walnut_alias(self):
        self.assertTrue(colors_match("Hazel", "лесной орех"))
        self.assertTrue(colors_match("Hazel", "ореховый"))
        self.assertFalse(colors_match("Hazel", "Walnut"))

    def test_titanium_variants_are_strict(self):
        self.assertTrue(
            colors_match("Natural Titanium", "натуральный титан")
        )
        self.assertTrue(
            colors_match("Natural Titanium", "титановый натуральный")
        )
        self.assertFalse(
            colors_match("Natural Titanium", "Blue Titanium")
        )
        self.assertFalse(
            colors_match("Black Titanium", "White Titanium")
        )
        self.assertTrue(
            colors_match("Titanium Gray", "титановый серый")
        )
        self.assertFalse(
            colors_match("Titanium Gray", "Titanium Black")
        )

    def test_other_marketing_variants_are_normalized(self):
        cases = [
            ("Moonstone", "лунный камень"),
            ("Ocean Blue", "океанский синий"),
            ("Forest Green", "лесной зелёный"),
            ("Phantom Black", "фантомный чёрный"),
            ("Midnight Black", "полуночный чёрный"),
        ]
        for requested, candidate in cases:
            with self.subTest(requested=requested):
                self.assertTrue(colors_match(requested, candidate))

    def test_base_color_has_lower_confidence(self):
        identity = normalize_color("зелёный")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.family, "green")
        self.assertEqual(identity.confidence, BASE_COLOR)
        self.assertTrue(colors_match("green", "Mint"))
        self.assertFalse(colors_match("Mint", "green"))

    def test_explicit_suffix_does_not_remove_model_words(self):
        self.assertIsNone(extract_color_phrase("Black Shark 5 Pro 12GB/256GB"))
        self.assertEqual(
            extract_color_phrase("Black Shark 5 Pro 12GB/256GB Black"),
            "Black",
        )
        identity = extract_color_identity(
            "Google Pixel 8 8GB/128GB (мятно-зелёный)"
        )
        self.assertIsNotNone(identity)
        self.assertEqual(identity.variant, "mint")

    def test_unknown_color_fails_closed_for_strict_selection(self):
        self.assertFalse(colors_match("Mint", "Aurora Glow"))
        self.assertFalse(colors_match("Aurora Glow", "Mint"))
        self.assertTrue(colors_match(None, "Hazel"))


if __name__ == "__main__":
    unittest.main()
