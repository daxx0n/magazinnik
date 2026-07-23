import unittest

from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_selection import model_version_signature


class ModelVersionSignatureTest(unittest.TestCase):
    def test_localized_and_english_aliases_have_one_identity(self) -> None:
        cases = (
            ("Lite", "lite"),
            ("Light", "lite"),
            ("Лайт", "lite"),
            ("Mini", "mini"),
            ("Мини", "mini"),
            ("Pro", "pro"),
            ("Про", "pro"),
            ("Max", "max"),
            ("Макс", "max"),
            ("Plus", "plus"),
            ("Плюс", "plus"),
            ("Ultra", "ultra"),
            ("Ультра", "ultra"),
        )
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(
                    model_version_signature(f"Brand Model {title}"),
                    frozenset({expected}),
                )

    def test_display_technology_and_light_color_are_not_model_tiers(self) -> None:
        self.assertEqual(
            model_version_signature("MiniLED телевизор LG QNED70"),
            frozenset(),
        )
        self.assertEqual(
            model_version_signature("Samsung Galaxy A55 Light Blue"),
            frozenset(),
        )

    def test_esim_is_not_tier_e_but_compact_model_suffix_is(self) -> None:
        self.assertEqual(
            model_version_signature("Apple iPhone 16 e SIM"),
            frozenset(),
        )
        self.assertEqual(
            model_version_signature("Apple iPhone 16 eSIM"),
            frozenset(),
        )
        self.assertEqual(
            model_version_signature("Apple iPhone 16e"),
            frozenset({"e"}),
        )


class CrossSourceMiniLightRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CatalogFirstPriceService(
            catalog_search_enabled=False,
            catalog_presentation_enabled=False,
        )

    def reason(self, requested: str, candidate: str) -> str | None:
        return self.service._model_mismatch_reason(
            canonical_title=requested,
            candidate_title=candidate,
            requested_title=requested,
        )

    def test_station_light_and_station_mini_are_different_models(self) -> None:
        requested = "Яндекс Станция Лайт 2 без часов (синий)"
        candidates = (
            "Умная колонка Яндекс Станция Мини 2 без часов (синий)",
            "Умная колонка Yandex Station Mini 2 without clock (Blue)",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertEqual(self.reason(requested, candidate), "version")

    def test_lite_light_and_cyrillic_light_are_the_same_tier(self) -> None:
        requested = "Яндекс Станция Лайт 2 без часов (синий)"
        candidates = (
            "Умная колонка Yandex Station Lite 2 without clock (Blue)",
            "Умная колонка Yandex Station Light 2 without clock (Blue)",
            "Умная колонка Яндекс Станция Лайт 2 без часов (синий)",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertIsNone(self.reason(requested, candidate))

    def test_rule_is_not_specific_to_yandex(self) -> None:
        self.assertEqual(
            self.reason("Apple iPad Mini 7", "Apple iPad Air 7"),
            "version",
        )
        self.assertEqual(
            self.reason("Xiaomi Pad 6 Lite", "Xiaomi Pad 6 Pro"),
            "version",
        )
        self.assertIsNone(
            self.reason("Xiaomi Pad 6 Lite", "Xiaomi Pad 6 Лайт")
        )


if __name__ == "__main__":
    unittest.main()
