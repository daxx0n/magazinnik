import unittest
from unittest.mock import AsyncMock, Mock

from app.models.offer import ProductOffer
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_code_matching import (
    allows_omitted_model_code,
    explicit_long_model_codes,
    short_marketing_model_codes,
)


ONLINER_BLACK = "Huawei nova Y63 GFY-LX1 6GB/128GB (черный)"
TWENTY_ONE_BLACK = "Смартфон Huawei Nova Y63 6GB/128GB (черный)"
TWENTY_ONE_SILVER = "Смартфон Huawei Nova Y63 6GB/128GB (серебристый)"


def offer(source: str, title: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{source.casefold()}",
        seller=source,
    )


class HuaweiY63ModelCodeFallbackTest(unittest.IsolatedAsyncioTestCase):
    def test_detects_long_code_and_shared_marketing_model(self) -> None:
        self.assertEqual(
            explicit_long_model_codes(ONLINER_BLACK),
            {"gfylx1"},
        )
        self.assertEqual(
            explicit_long_model_codes(TWENTY_ONE_BLACK),
            set(),
        )
        self.assertEqual(
            short_marketing_model_codes(ONLINER_BLACK),
            {"y63"},
        )
        self.assertEqual(
            short_marketing_model_codes(TWENTY_ONE_BLACK),
            {"y63"},
        )

    def test_allows_21vek_title_that_only_omits_gfy_lx1(self) -> None:
        self.assertTrue(
            allows_omitted_model_code(
                requested_title=ONLINER_BLACK,
                candidate_title=TWENTY_ONE_BLACK,
            )
        )
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=ONLINER_BLACK,
                candidate_title=TWENTY_ONE_BLACK,
                requested_title=ONLINER_BLACK,
            )
        )

    def test_explicit_different_long_code_remains_rejected(self) -> None:
        candidate = (
            "Смартфон Huawei Nova Y63 ABC-LX9 "
            "6GB/128GB (черный)"
        )
        self.assertFalse(
            allows_omitted_model_code(
                requested_title=ONLINER_BLACK,
                candidate_title=candidate,
            )
        )
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=ONLINER_BLACK,
                candidate_title=candidate,
                requested_title=ONLINER_BLACK,
            ),
            "model_code",
        )

    def test_different_memory_or_marketing_model_remains_rejected(self) -> None:
        for candidate in (
            "Смартфон Huawei Nova Y63 4GB/128GB (черный)",
            "Смартфон Huawei Nova Y61 6GB/128GB (черный)",
            "Смартфон Huawei Nova Y63 128GB (черный)",
        ):
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    allows_omitted_model_code(
                        requested_title=ONLINER_BLACK,
                        candidate_title=candidate,
                    )
                )
                self.assertIsNotNone(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical_title=ONLINER_BLACK,
                        candidate_title=candidate,
                        requested_title=ONLINER_BLACK,
                    )
                )

    def test_color_filter_stays_strict_after_code_fallback(self) -> None:
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=ONLINER_BLACK,
                candidate_title=TWENTY_ONE_SILVER,
                requested_title=ONLINER_BLACK,
            ),
            "color",
        )

    async def test_aggregate_marks_21vek_as_found(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=Mock(
                total_offers=2,
                created_products=0,
                merged_offers=0,
                updated_offers=0,
                product_keys=(),
            )
        )
        service = CatalogFirstPriceService(
            catalog_service=catalog_service,
            catalog_search_enabled=False,
            catalog_presentation_enabled=False,
        )
        service._onliner_queries["novay636128bk"] = "huawei nova y63 6/128"
        service.search_onliner_key = AsyncMock(
            return_value=[offer("Onliner", ONLINER_BLACK, 549.0)]
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=([], False, [])
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[offer("21vek", TWENTY_ONE_BLACK, 499.0)]
        )
        service._search_shop_by_query = AsyncMock(return_value=[])
        service._search_electrosila_query = AsyncMock(return_value=[])
        service._search_zeon_query = AsyncMock(return_value=[])

        result = await service.search_all_sources_by_onliner_key(
            "novay636128bk"
        )

        self.assertEqual(
            [item.source for item in result.offers],
            ["21vek", "Onliner"],
        )
        twenty_one_status = next(
            status
            for status in result.source_statuses
            if status.source == "21vek"
        )
        self.assertEqual(twenty_one_status.state, "found")
        self.assertEqual(twenty_one_status.matched_offers, 1)
        self.assertEqual(twenty_one_status.checked_candidates, 1)
        twenty_one_decision = next(
            decision
            for decision in result.match_decisions
            if decision.source == "21vek"
        )
        self.assertTrue(twenty_one_decision.accepted)
        self.assertEqual(twenty_one_decision.reason, "exact_match")


if __name__ == "__main__":
    unittest.main()
