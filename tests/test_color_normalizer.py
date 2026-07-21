import unittest

from app.services.color_normalizer import colors_match, normalize_color


class ColorNormalizerTest(unittest.TestCase):
    def test_pixel_mint_matches_multilingual_aliases(self):
        self.assertTrue(colors_match("мятный зеленый", "Mint"))
        self.assertTrue(colors_match("Mint green", "мятный"))

    def test_different_pixel_color_is_not_exact_variant(self):
        self.assertFalse(colors_match("mint", "hazel"))
        self.assertFalse(colors_match("mint", "obsidian"))

    def test_same_family_different_variant_is_not_match(self):
        self.assertFalse(colors_match("green", "mint"))
        self.assertFalse(colors_match("mint", "jade"))

    def test_brand_color_aliases(self):
        self.assertEqual(normalize_color("Obsidian").family, "black")
        self.assertEqual(normalize_color("Natural Titanium"), None)
        self.assertEqual(normalize_color("лунный камень").family, "gray")

    def test_hazel_variants(self):
        self.assertTrue(colors_match("лесной орех", "Hazel"))
        self.assertFalse(colors_match("мятный зеленый", "Hazel"))


if __name__ == "__main__":
    unittest.main()
