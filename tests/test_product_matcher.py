import unittest

from app.models.catalog import MatchLevel, ProductIdentity
from app.services.product_matcher import ProductMatcher


class ProductMatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.matcher = ProductMatcher()

    def test_matches_same_ean_exactly(self) -> None:
        result = self.matcher.match(
            ProductIdentity(
                brand="Apple",
                model="iPhone 17 Pro",
                memory="256GB",
                ean="0195950123456",
            ),
            ProductIdentity(
                brand="Apple",
                model="iPhone 17 Pro",
                memory="256 GB",
                ean="0195950123456",
            ),
        )

        self.assertEqual(result.level, MatchLevel.EXACT)
        self.assertEqual(result.reason, "same_ean")
        self.assertEqual(result.score, 1.0)

    def test_matches_same_mpn_exactly(self) -> None:
        result = self.matcher.match(
            ProductIdentity(
                brand="Bosch",
                model="HBA534EB3",
                mpn="HBA534EB3",
            ),
            ProductIdentity(
                brand="BOSCH",
                model="HBA 534 EB3",
                mpn="hba-534-eb3",
            ),
        )

        self.assertEqual(result.level, MatchLevel.EXACT)
        self.assertEqual(result.reason, "same_mpn")

    def test_rejects_memory_conflict_before_identifier_match(self) -> None:
        result = self.matcher.match(
            ProductIdentity(
                brand="Apple",
                model="iPhone 17",
                memory="256GB",
                ean="1234567890123",
            ),
            ProductIdentity(
                brand="Apple",
                model="iPhone 17",
                memory="512GB",
                ean="1234567890123",
            ),
        )

        self.assertEqual(result.level, MatchLevel.REJECTED)
        self.assertEqual(result.reason, "variant_conflict")
        self.assertEqual(result.conflicts, ("memory",))

    def test_rejects_pro_and_pro_max_as_different_models(self) -> None:
        result = self.matcher.match(
            ProductIdentity(
                brand="Apple",
                model="iPhone 17 Pro",
                memory="256GB",
            ),
            ProductIdentity(
                brand="Apple",
                model="iPhone 17 Pro Max",
                memory="256GB",
            ),
        )

        self.assertEqual(result.level, MatchLevel.REJECTED)
        self.assertIn("model", result.conflicts)

    def test_matches_formatting_variants(self) -> None:
        result = self.matcher.match(
            ProductIdentity(
                brand="Samsung",
                model="Galaxy S25 Ultra",
                memory="12GB/256GB",
                color="Titanium Black",
            ),
            ProductIdentity(
                brand="SAMSUNG",
                model="Galaxy-S25 Ultra",
                memory="12 GB / 256 GB",
                color="Titanium Black",
            ),
        )

        self.assertEqual(result.level, MatchLevel.EXACT)
        self.assertEqual(result.reason, "same_model_and_variant")

    def test_marks_missing_variant_as_probable(self) -> None:
        result = self.matcher.match(
            ProductIdentity(
                brand="Samsung",
                model="Galaxy S25",
                memory="256GB",
            ),
            ProductIdentity(
                brand="Samsung",
                model="Galaxy S25",
            ),
        )

        self.assertEqual(result.level, MatchLevel.PROBABLE)
        self.assertEqual(
            result.reason,
            "same_model_no_variant_conflicts",
        )

    def test_rejects_unrelated_products(self) -> None:
        result = self.matcher.match(
            ProductIdentity(
                brand="Apple",
                model="iPhone 17",
            ),
            ProductIdentity(
                brand="Bosch",
                model="HBA534EB3",
            ),
        )

        self.assertEqual(result.level, MatchLevel.REJECTED)
        self.assertEqual(result.reason, "different_product")


if __name__ == "__main__":
    unittest.main()
