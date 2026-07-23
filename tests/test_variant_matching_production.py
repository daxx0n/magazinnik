import unittest

from app.services.catalog_first_search import CatalogFirstPriceService


class VariantMatchingProductionTest(unittest.TestCase):
    def test_production_matcher_accepts_compatible_store_wording(self) -> None:
        cases = [
            (
                "Apple iPhone 17 Pro 256GB EU Dual SIM",
                "Смартфон Apple iPhone 17 Pro 12GB/256GB Dual SIM",
            ),
            (
                "Apple iPhone 17 Pro 256GB EU",
                "Apple iPhone 17 Pro 256GB EAC",
            ),
            (
                "Microsoft Xbox Series X 1TB",
                "Игровая приставка Microsoft Xbox Series X 1024GB",
            ),
            (
                "Samsung Galaxy Tab S10 256GB",
                "Samsung Galaxy Tab S10 256GB 5G Global",
            ),
            (
                "Apple iPhone 17 Pro 256GB",
                "Apple iPhone 17 Pro 256GB Dual eSIM",
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


if __name__ == "__main__":
    unittest.main()
