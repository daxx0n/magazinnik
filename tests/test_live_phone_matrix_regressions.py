import unittest
from unittest.mock import AsyncMock, Mock

from app.models.offer import ProductOffer
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_code_matching import (
    allows_omitted_model_code,
    marketing_identity_words,
)
from app.services.model_selection import (
    generation_mismatch,
    numeric_suffix_model_mismatch,
    numeric_suffix_model_tokens,
)


SPARK_40 = "Tecno Spark 40 8GB/256GB (чернильный черный)"
SPARK_40_STORE = (
    "Смартфон TECNO Spark 40 8GB/256GB KM5n "
    "(чернильный черный)"
)
SPARK_40C_STORE = "Смартфон TECNO Spark 40C 8GB/256GB (черный)"

PURA_80 = "Huawei Pura 80 HED-LX9 12GB/256GB (черный)"
PURA_80_STORE = "Смартфон Huawei Pura 80 12GB/256GB (черный)"
PURA_80_WHITE = "Смартфон Huawei Pura 80 12GB/256GB (белый)"


def offer(source: str, title: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{source.casefold()}/{price}",
        seller=source,
    )


def catalog_service() -> Mock:
    service = Mock()
    service.ingest_offers_with_report_async = AsyncMock(
        return_value=Mock(
            total_offers=3,
            created_products=0,
            merged_offers=0,
            updated_offers=0,
            product_keys=(),
        )
    )
    return service


def prepared_service() -> CatalogFirstPriceService:
    service = CatalogFirstPriceService(
        catalog_service=catalog_service(),
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    service._search_five_element_by_query = AsyncMock(
        return_value=([], False, [])
    )
    service._search_twenty_one_vek_by_query = AsyncMock(return_value=[])
    service._search_shop_by_query = AsyncMock(return_value=[])
    service._search_electrosila_query = AsyncMock(return_value=[])
    service._search_zeon_query = AsyncMock(return_value=[])
    return service


class NumericSuffixModelTest(unittest.TestCase):
    def test_extracts_marketing_suffixes_but_ignores_units(self) -> None:
        self.assertEqual(
            numeric_suffix_model_tokens(
                "Phone 40C 8GB/256GB 5G 120Hz 33W"
            ),
            {"40": {"40c"}},
        )

    def test_base_and_letter_suffix_are_different_models(self) -> None:
        pairs = (
            ("Tecno Spark 40", "Tecno Spark 40C"),
            ("Google Pixel 8", "Google Pixel 8a"),
            ("Apple iPhone 16", "Apple iPhone 16e"),
            ("Xiaomi 14", "Xiaomi 14T"),
        )
        for base, suffixed in pairs:
            with self.subTest(base=base, suffixed=suffixed):
                self.assertTrue(
                    numeric_suffix_model_mismatch(base, suffixed)
                )
                self.assertTrue(
                    numeric_suffix_model_mismatch(suffixed, base)
                )
                self.assertTrue(
                    generation_mismatch(base, suffixed)
                )
                self.assertTrue(
                    generation_mismatch(suffixed, base)
                )

    def test_same_suffix_is_compatible(self) -> None:
        self.assertFalse(
            generation_mismatch(
                "Google Pixel 8a 8GB/128GB",
                "Смартфон Google Pixel 8A 8GB/128GB",
            )
        )

    def test_spark_40c_is_rejected_by_production_matcher(self) -> None:
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=SPARK_40,
                candidate_title=SPARK_40C_STORE,
                requested_title=SPARK_40,
            ),
            "model_number",
        )
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=SPARK_40,
                candidate_title=SPARK_40_STORE,
                requested_title=SPARK_40,
            )
        )


class NumericModelCodeFallbackTest(unittest.TestCase):
    def test_allows_numeric_model_when_only_long_code_is_omitted(self) -> None:
        self.assertEqual(
            marketing_identity_words(PURA_80),
            ("huawei", "pura"),
        )
        self.assertEqual(
            marketing_identity_words(PURA_80_STORE),
            ("huawei", "pura"),
        )
        self.assertTrue(
            allows_omitted_model_code(PURA_80, PURA_80_STORE)
        )
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=PURA_80,
                candidate_title=PURA_80_STORE,
                requested_title=PURA_80,
            )
        )

    def test_optional_leading_brand_is_supported_generically(self) -> None:
        self.assertTrue(
            allows_omitted_model_code(
                "Apple iPhone 17 A3298 256GB (black)",
                "iPhone 17 256GB (black)",
            )
        )

    def test_different_family_memory_and_explicit_code_remain_rejected(self) -> None:
        cases = (
            "Смартфон Huawei Mate 80 12GB/256GB (черный)",
            "Смартфон Huawei Pura 80 8GB/256GB (черный)",
            "Смартфон Huawei Pura 80 ABC-LX1 12GB/256GB (черный)",
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    allows_omitted_model_code(PURA_80, candidate)
                )
                self.assertEqual(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical_title=PURA_80,
                        candidate_title=candidate,
                        requested_title=PURA_80,
                    ),
                    "model_code",
                )

    def test_color_is_checked_after_model_code_fallback(self) -> None:
        self.assertTrue(
            allows_omitted_model_code(PURA_80, PURA_80_WHITE)
        )
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=PURA_80,
                candidate_title=PURA_80_WHITE,
                requested_title=PURA_80,
            ),
            "color",
        )


class LiveMatrixAggregateRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def test_cheaper_spark_40c_is_not_accepted_as_spark_40(self) -> None:
        service = prepared_service()
        service._onliner_queries["spark40"] = "Tecno Spark 40 8/256"
        service.search_onliner_key = AsyncMock(
            return_value=[offer("Onliner", SPARK_40, 499.0)]
        )
        service._search_electrosila_query = AsyncMock(
            return_value=[
                offer("Electrosila", SPARK_40C_STORE, 399.0),
                offer("Electrosila", SPARK_40_STORE, 449.0),
            ]
        )

        result = await service.search_all_sources_by_onliner_key("spark40")

        self.assertEqual(
            [(item.source, item.title) for item in result.offers],
            [
                ("Electrosila", SPARK_40_STORE),
                ("Onliner", SPARK_40),
            ],
        )
        status = next(
            item
            for item in result.source_statuses
            if item.source == "Электросила"
        )
        self.assertEqual(status.state, "found")
        self.assertEqual(status.checked_candidates, 2)
        self.assertEqual(status.matched_offers, 1)
        wrong = next(
            item
            for item in result.match_decisions
            if item.title == SPARK_40C_STORE
        )
        self.assertFalse(wrong.accepted)
        self.assertEqual(wrong.reason, "model_number")

    async def test_pura_80_without_store_code_is_found(self) -> None:
        service = prepared_service()
        service._onliner_queries["pura80"] = "Huawei Pura 80 12/256"
        service.search_onliner_key = AsyncMock(
            return_value=[offer("Onliner", PURA_80, 1799.0)]
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[
                offer("21vek", PURA_80_STORE, 1699.0),
                offer("21vek", PURA_80_WHITE, 1650.0),
            ]
        )

        result = await service.search_all_sources_by_onliner_key("pura80")

        self.assertEqual(
            [(item.source, item.title) for item in result.offers],
            [
                ("21vek", PURA_80_STORE),
                ("Onliner", PURA_80),
            ],
        )
        status = next(
            item
            for item in result.source_statuses
            if item.source == "21vek"
        )
        self.assertEqual(status.state, "found")
        self.assertEqual(status.checked_candidates, 2)
        self.assertEqual(status.matched_offers, 1)


if __name__ == "__main__":
    unittest.main()
