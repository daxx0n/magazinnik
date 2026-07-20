import random
import string
import unittest

from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.search_input import (
    SearchInputError,
    normalize_search_query,
)


class MatchingFuzzTest(unittest.TestCase):
    def test_equivalent_store_wording_is_accepted(self) -> None:
        cases = [
            (
                "Google Pixel 8 8GB/128GB (Obsidian)",
                "Смартфон Google Pixel 8 8/128 ГБ черный",
            ),
            (
                "Samsung Galaxy S25 12GB/256GB Navy",
                "Телефон SAMSUNG Galaxy S25 12/256GB темно-синий",
            ),
            (
                "Apple iPhone 15 Pro 256GB Natural Titanium",
                "Смартфон Apple iPhone 15 Pro 256 ГБ природный титан",
            ),
            (
                "Bosch HBA-534-EB3 Black",
                "Духовой шкаф Bosch HBA534EB3 черный",
            ),
            (
                "Sony PlayStation 5 Slim Digital Edition White",
                "Игровая консоль Sony PS5 Slim без дисковода белая",
            ),
        ]

        for canonical, candidate in cases:
            with self.subTest(canonical=canonical, candidate=candidate):
                self.assertIsNone(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    )
                )

    def test_real_variant_differences_are_rejected(self) -> None:
        canonical = "Samsung Galaxy S25 12GB/256GB Navy"
        cases = {
            "Samsung Galaxy S24 12GB/256GB Navy": "model_number",
            "Samsung Galaxy S25 12GB/128GB Navy": "memory",
            "Samsung Galaxy S25 Ultra 12GB/256GB Navy": "version",
            "Samsung Galaxy S25 12GB/256GB Black": "color",
            "Samsung Galaxy S25 12GB/256GB Navy refurbished": "condition",
            "Samsung Galaxy S25 12GB/256GB Navy + Watch": "bundle",
        }

        for candidate, expected in cases.items():
            with self.subTest(candidate=candidate):
                self.assertEqual(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    ),
                    expected,
                )

    def test_case_and_spacing_variants_do_not_change_match(self) -> None:
        canonical = "Google Pixel 8 8GB/128GB (Obsidian)"
        base = "Телефон Google Pixel 8 8/128 ГБ черный"
        randomizer = random.Random(20260720)

        for index in range(100):
            words = base.split()
            transformed = []
            for word in words:
                variant = "".join(
                    character.upper()
                    if randomizer.random() < 0.5
                    else character.lower()
                    for character in word
                )
                transformed.append(variant)
            separator = " " * randomizer.randint(1, 5)
            candidate = separator.join(transformed)
            with self.subTest(index=index, candidate=candidate):
                self.assertIsNone(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    )
                )

    def test_two_hundred_dirty_unicode_queries_are_safe_and_deterministic(
        self,
    ) -> None:
        randomizer = random.Random(20260720)
        alphabet = (
            string.ascii_letters
            + string.digits
            + "абвгдежзийклмнопрстуфхцчшщэюя"
            + " -_/().,+"
            + "\u200b\u200c\u2060\x00\x1f\t\n"
        )

        for index in range(200):
            dirty = "Pixel 8 " + "".join(
                randomizer.choice(alphabet)
                for _ in range(randomizer.randint(0, 80))
            )
            with self.subTest(index=index):
                try:
                    first = normalize_search_query(dirty)
                    second = normalize_search_query(dirty)
                except SearchInputError:
                    continue
                self.assertEqual(first, second)
                self.assertTrue(any(character.isalnum() for character in first))
                self.assertNotIn("\x00", first)
                self.assertNotIn("\u200b", first)
                self.assertLessEqual(len(first), 200)

    def test_matcher_never_throws_for_random_candidate_titles(self) -> None:
        randomizer = random.Random(20260720)
        canonical = "Apple iPhone 15 Pro 256GB Black"
        tokens = [
            "Apple",
            "iPhone",
            "15",
            "14",
            "Pro",
            "Plus",
            "256GB",
            "128GB",
            "Black",
            "Blue",
            "refurbished",
            "чехол",
            "+",
            "Watch",
            "Global",
            "eSIM",
        ]

        for index in range(300):
            candidate = " ".join(
                randomizer.choice(tokens)
                for _ in range(randomizer.randint(1, 12))
            )
            with self.subTest(index=index, candidate=candidate):
                result = CatalogFirstPriceService._model_mismatch_reason(
                    canonical,
                    candidate,
                    requested_title=canonical,
                )
                self.assertTrue(result is None or isinstance(result, str))


if __name__ == "__main__":
    unittest.main()
