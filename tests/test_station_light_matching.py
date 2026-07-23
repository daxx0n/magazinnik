import unittest

from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_code_matching import technical_model_code_words
from app.services.variant_matching import (
    clock_display_configuration,
    neutralize_variant_markers,
)


REQUESTED = "Яндекс Станция Лайт 2 без часов (синий)"


class TechnicalCodeBrandTest(unittest.TestCase):
    def test_separated_model_code_words_are_not_brand_candidates(self) -> None:
        self.assertEqual(
            technical_model_code_words(
                "Умная колонка Яндекс Станция Лайт 2 YNDX-00028BLU"
            ),
            {"yndx"},
        )
        self.assertEqual(
            technical_model_code_words("Huawei nova Y63 GFY-LX1 6GB/128GB"),
            {"gfy"},
        )


class ClockDisplayConfigurationTest(unittest.TestCase):
    def test_detects_explicit_positive_and_negative_forms(self) -> None:
        self.assertEqual(
            clock_display_configuration("Станция Лайт 2 без часов"),
            "without_display",
        )
        self.assertEqual(
            clock_display_configuration("Smart speaker with clock"),
            "with_display",
        )
        self.assertEqual(
            clock_display_configuration("Колонка с дисплеем"),
            "with_display",
        )
        self.assertEqual(
            clock_display_configuration("Колонка без экрана"),
            "without_display",
        )
        self.assertIsNone(clock_display_configuration("Станция Лайт 2"))

    def test_neutralization_removes_display_variant_words(self) -> None:
        self.assertEqual(
            neutralize_variant_markers("Яндекс Станция Лайт 2 без часов"),
            "Яндекс Станция Лайт 2",
        )


class StationLightCrossSourceRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CatalogFirstPriceService(
            catalog_search_enabled=False,
            catalog_presentation_enabled=False,
        )

    def reason(self, candidate: str) -> str | None:
        return self.service._model_mismatch_reason(
            canonical_title=REQUESTED,
            candidate_title=candidate,
            requested_title=REQUESTED,
        )

    def test_accepts_real_no_clock_titles_from_all_reported_sources(self) -> None:
        candidates = (
            "Умная колонка Яндекс Станция Лайт 2 без часов / "
            "YNDX-00028BLU (синий)",
            "Яндекс Умная колонка Яндекс.Станция Лайт 2 без часов "
            "(YNDX-00028BLU) синий",
            "Умная колонка YANDEX Яндекс Станция Лайт 2 "
            "YNDX-00028 (синий, без часов)",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertIsNone(self.reason(candidate))

    def test_rejects_clock_variant_when_no_clock_was_selected(self) -> None:
        candidates = (
            "Умная колонка Яндекс Станция Лайт 2 YNDX-00026BLU (синий)",
            "Умная колонка YANDEX Яндекс Станция Лайт 2 "
            "YNDX-00026 (синий)",
            "Яндекс Станция Лайт 2 с часами (синий)",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertEqual(self.reason(candidate), "configuration")

    def test_one_sided_explicit_display_variant_is_not_silently_merged(self) -> None:
        base = "Яндекс Станция Лайт 2 (синий)"
        self.assertEqual(
            self.service._model_mismatch_reason(
                canonical_title=base,
                candidate_title=(
                    "Умная колонка Яндекс Станция Лайт 2 без часов "
                    "YNDX-00028BLU (синий)"
                ),
                requested_title=base,
            ),
            "configuration",
        )


if __name__ == "__main__":
    unittest.main()
