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

    def test_rejects_memory_region_sim_and_device_configuration(self) -> None:
        cases = [
            (
                "Apple iPhone 17 Pro 256GB",
                "Apple iPhone 17 Pro 512GB",
                "memory",
            ),
            (
                "Apple iPhone 17 Pro 256GB EU",
                "Apple iPhone 17 Pro 256GB US",
                "region",
            ),
            (
                "Apple iPhone 17 Pro 256GB Dual SIM",
                "Apple iPhone 17 Pro 256GB eSIM only",
                "sim",
            ),
            (
                "Samsung Galaxy Tab S10 256GB 4G",
                "Samsung Galaxy Tab S10 256GB 5G",
                "configuration",
            ),
            (
                "Sony PlayStation 5 Slim Digital Edition",
                "Sony PlayStation 5 Slim с дисководом",
                "configuration",
            ),
        ]
        for canonical, candidate, expected in cases:
            with self.subTest(canonical=canonical, candidate=candidate):
                self.assertEqual(
                    CatalogFirstPriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=canonical,
                    ),
                    expected,
                )

    def test_rejects_connector_difference(self) -> None:
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                "Apple AirPods Pro 2 Lightning",
                "Apple AirPods Pro 2 USB Type-C",
                requested_title="Apple AirPods Pro 2 Lightning",
            ),
            "configuration",
        )


if __name__ == "__main__":
    unittest.main()
