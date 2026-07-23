import unittest
from unittest.mock import AsyncMock, Mock

from app.models.offer import ProductOffer
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.model_code_matching import (
    explicit_model_code_mismatch,
    most_specific_model_codes,
)
from app.sources.zeon import ZeonSource


CANONICAL = "LG QNED AI QNED70 50QNED70B6C"
EXACT = "Телевизор LG QNED AI QNED70 50QNED70B6C"
WRONG = "Телевизор LG QNED AI QNED70 86QNED70A6A"


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


class ExplicitFullModelCodeTest(unittest.TestCase):
    def test_family_code_is_removed_when_full_code_contains_it(self) -> None:
        self.assertEqual(
            most_specific_model_codes(CANONICAL),
            {"50qned70b6c"},
        )
        self.assertEqual(
            most_specific_model_codes(WRONG),
            {"86qned70a6a"},
        )

    def test_different_full_codes_are_rejected(self) -> None:
        pairs = (
            (CANONICAL, WRONG),
            ("TCL 55C745", "TCL 65C745"),
            ("Hisense 65U7KQ", "Hisense 75U7KQ"),
        )
        for requested, candidate in pairs:
            with self.subTest(requested=requested, candidate=candidate):
                self.assertTrue(
                    explicit_model_code_mismatch(requested, candidate)
                )

    def test_exact_and_regional_suffix_codes_remain_compatible(self) -> None:
        self.assertFalse(explicit_model_code_mismatch(CANONICAL, EXACT))
        self.assertFalse(
            explicit_model_code_mismatch(
                "Samsung Galaxy S25 SM-S931B",
                "Samsung Galaxy S25 SM-S931B/DS",
            )
        )

    def test_display_technology_prefix_does_not_replace_brand(self) -> None:
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=CANONICAL,
                candidate_title="MiniLED телевизор LG QNED AI QNED70 50QNED70B6C",
                requested_title=CANONICAL,
            )
        )
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=CANONICAL,
                candidate_title="OLED телевизор Samsung 50QNED70B6C",
                requested_title=CANONICAL,
            ),
            "brand",
        )

    def test_catalog_matcher_rejects_wrong_diagonal(self) -> None:
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=CANONICAL,
                candidate_title=WRONG,
                requested_title=CANONICAL,
            ),
            "model_code",
        )
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=CANONICAL,
                candidate_title=EXACT,
                requested_title=CANONICAL,
            )
        )


class ZeonNumericPrefixIdentifierTest(unittest.TestCase):
    def test_full_numeric_prefix_code_is_prioritized(self) -> None:
        variants = ZeonSource._query_variants(CANONICAL)
        self.assertEqual(variants[0], ("50QNED70B6C", True))
        identifiers = [
            value.casefold()
            for value, is_identifier in variants
            if is_identifier
        ]
        self.assertNotIn("qned70", identifiers)

    def test_other_numeric_prefix_codes_are_supported(self) -> None:
        for code in ("55C745", "65U7KQ", "24F34B"):
            with self.subTest(code=code):
                self.assertEqual(
                    ZeonSource._query_variants(f"TV Brand {code}")[0],
                    (code, True),
                )


class FullModelCodeAggregateTest(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_zeon_model_is_filtered(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=Mock(
                total_offers=3,
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
        service._onliner_queries["lg50"] = "50QNED70B6C"
        service.search_onliner_key = AsyncMock(
            return_value=[offer("Onliner", CANONICAL, 1734.90)]
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=([], False, [])
        )
        service._search_twenty_one_vek_by_query = AsyncMock(return_value=[])
        service._search_shop_by_query = AsyncMock(return_value=[])
        service._search_electrosila_query = AsyncMock(return_value=[])
        service._search_zeon_query = AsyncMock(
            return_value=[
                offer("Zeon", WRONG, 4049.0),
                offer("Zeon", EXACT, 1999.0),
            ]
        )

        result = await service.search_all_sources_by_onliner_key("lg50")

        self.assertEqual(
            [(item.source, item.title) for item in result.offers],
            [("Onliner", CANONICAL), ("Zeon", EXACT)],
        )
        wrong = next(
            item for item in result.match_decisions if item.title == WRONG
        )
        self.assertFalse(wrong.accepted)
        self.assertEqual(wrong.reason, "model_code")
        zeon_status = next(
            item for item in result.source_statuses if item.source == "Zeon"
        )
        self.assertEqual(zeon_status.state, "found")
        self.assertEqual(zeon_status.checked_candidates, 2)
        self.assertEqual(zeon_status.matched_offers, 1)


if __name__ == "__main__":
    unittest.main()
