import unittest

from app.services.color_normalizer import colors_match, normalize_color


class ColorNormalizerTest(unittest.TestCase):
    def test_pixel_mint_matches_multilingual_aliases(self):
        self.assertTrue(colors_match("мятный зеленый", "Mint"))
        self.assertTrue(colors_match("Mint green", "мятный"))

    def test_different_pixel_color_is_not_exact_variant(self):
        self.assertFalse(colors_match("mint", "hazel"))
        self.assertFalse(colors_match("mint", "obsidian"))

    def test_brand_color_aliases(self):
        self.assertEqual(normalize_color("Obsidian").family, "black")
        self.assertEqual(normalize_color("Natural Titanium").family, None)
        self.assertEqual(normalize_color("лунный камень").family, "gray")


if __name__ == "__main__":
    unittest.main()
