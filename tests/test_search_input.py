import unittest

from app.services.search_input import (
    SearchInputError,
    normalize_search_query,
)


class SearchInputTest(unittest.TestCase):
    def test_normalizes_unicode_and_whitespace(self) -> None:
        self.assertEqual(
            normalize_search_query("  Ｇｏｏｇｌｅ\u200b   Pixel\n8  "),
            "Google Pixel 8",
        )

    def test_removes_control_characters(self) -> None:
        self.assertEqual(
            normalize_search_query("Pixel\x00\x1f 8"),
            "Pixel 8",
        )

    def test_rejects_punctuation_only(self) -> None:
        with self.assertRaises(SearchInputError):
            normalize_search_query("--- !!!")

    def test_rejects_too_short_after_normalization(self) -> None:
        with self.assertRaises(SearchInputError):
            normalize_search_query("  a \u200b ")

    def test_rejects_oversized_query(self) -> None:
        with self.assertRaises(SearchInputError):
            normalize_search_query("Pixel " + "x" * 300, max_length=200)

    def test_accepts_cyrillic_and_model_code(self) -> None:
        self.assertEqual(
            normalize_search_query("  Духовой шкаф Bosch HBA-534-EB3 "),
            "Духовой шкаф Bosch HBA-534-EB3",
        )


if __name__ == "__main__":
    unittest.main()
