from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise RuntimeError(
            f"Expected one match in {path}, found {content.count(old)}"
        )
    file_path.write_text(content.replace(old, new, 1), encoding="utf-8")


replace_once(
    "app/services/model_code_matching.py",
    '''_MEMORY_TOKEN_RE = re.compile(
    r"\\d+(?:gb|tb|mb|гб|тб|мб)",
    re.IGNORECASE,
)
''',
    '''_MEMORY_TOKEN_RE = re.compile(
    r"\\d+(?:gb|tb|mb|гб|тб|мб)",
    re.IGNORECASE,
)
_MEASUREMENT_CODE_RE = re.compile(
    r"\\d+(?:gb|tb|mb|гб|тб|мб|hz|khz|mhz|ghz|"
    r"w|kw|v|mah|mp|g|k)",
    re.IGNORECASE,
)
''',
)

replace_once(
    "app/services/model_code_matching.py",
    '''def short_marketing_model_codes(value: str) -> set[str]:
''',
    '''def _compatible_explicit_model_codes(first: str, second: str) -> bool:
    if first == second:
        return True

    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= 5 and longer.endswith(shorter):
        return True
    if not longer.startswith(shorter):
        return False

    regional_suffix = longer[len(shorter):]
    supports_regional_suffix = bool(
        re.fullmatch(
            r"(?:sm[a-z]\\d{3,4}[a-z]|[mnfp][a-z0-9]{4})",
            shorter,
        )
    )
    return (
        supports_regional_suffix
        and len(regional_suffix) >= 2
        and bool(re.search(r"[a-zа-я]", regional_suffix))
    )


def most_specific_model_codes(value: str) -> set[str]:
    """Returns strongest explicit codes, dropping specs and family substrings."""

    codes = {
        code
        for code in explicit_long_model_codes(value)
        if (
            code not in _IGNORED_SHORT_CODES
            and _MEASUREMENT_CODE_RE.fullmatch(code) is None
        )
    }
    return {
        code
        for code in codes
        if not any(
            code != other and code in other
            for other in codes
        )
    }


def explicit_model_code_mismatch(
    requested_title: str,
    candidate_title: str,
) -> bool:
    """Rejects different explicit full codes even when a family token matches."""

    requested_codes = most_specific_model_codes(requested_title)
    candidate_codes = most_specific_model_codes(candidate_title)
    if not requested_codes or not candidate_codes:
        return False

    return not any(
        _compatible_explicit_model_codes(requested, candidate)
        for requested in requested_codes
        for candidate in candidate_codes
    )


def short_marketing_model_codes(value: str) -> set[str]:
''',
)

replace_once(
    "app/services/catalog_first_search.py",
    "from app.services.model_code_matching import allows_omitted_model_code\n",
    '''from app.services.model_code_matching import (
    allows_omitted_model_code,
    explicit_model_code_mismatch,
)
''',
)

replace_once(
    "app/services/catalog_first_search.py",
    '''        if generation_mismatch(
            canonical_title=canonical_title,
            candidate_title=candidate_title,
            requested_title=reference_title,
        ):
            return "model_number"

        reference_color = requested_color_key(reference_title)
''',
    '''        if generation_mismatch(
            canonical_title=canonical_title,
            candidate_title=candidate_title,
            requested_title=reference_title,
        ):
            return "model_number"
        if explicit_model_code_mismatch(
            requested_title=reference_title,
            candidate_title=candidate_title,
        ):
            return "model_code"

        reference_color = requested_color_key(reference_title)
''',
)

replace_once(
    "app/sources/zeon.py",
    '''            has_separator = any(character in token for character in "-_/." )
            if not has_separator and not token[0].isalpha():
                continue
            if len(compact) < 2:
                continue
            identifiers.append(token)

        return sorted(
            dict.fromkeys(identifiers),
            key=lambda value: (
                any(character in value for character in "-_/.") ,
                len(re.sub(r"[^a-zа-я0-9]", "", value.casefold())),
            ),
            reverse=True,
        )
'''.replace('"-_/.\") ,', '"-_/.\"),'),
    '''            has_separator = any(character in token for character in "-_/.")
            starts_with_letter = token[0].isalpha()
            numeric_prefix_identifier = (
                not starts_with_letter
                and len(compact) >= 5
                and sum(character.isdigit() for character in compact) >= 3
            )
            if (
                not has_separator
                and not starts_with_letter
                and not numeric_prefix_identifier
            ):
                continue
            if len(compact) < 2:
                continue
            identifiers.append(token)

        ordered = sorted(
            dict.fromkeys(identifiers),
            key=lambda value: (
                any(character in value for character in "-_/.") ,
                len(re.sub(r"[^a-zа-я0-9]", "", value.casefold())),
            ),
            reverse=True,
        )
        compact_values = {
            value: re.sub(r"[^a-zа-я0-9]", "", value.casefold())
            for value in ordered
        }
        return [
            value
            for value in ordered
            if not any(
                compact_values[value] != compact_values[other]
                and compact_values[value] in compact_values[other]
                for other in ordered
            )
        ]
'''.replace('"-_/.\") ,', '"-_/.\"),'),
)

Path("tests/test_full_model_code_matching.py").write_text(
    '''import unittest
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
''',
    encoding="utf-8",
)

Path("scripts/apply_full_model_code_fix.py").unlink()
Path(".github/workflows/apply-full-model-code-fix.yml").unlink()
