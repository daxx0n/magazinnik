import unittest

from app.models.offer import ProductOffer
from app.services.catalog_service import CatalogService


class CatalogMetricsTest(unittest.TestCase):
    @staticmethod
    def offer(
        source: str,
        title: str,
        suffix: str,
        price: float,
    ) -> ProductOffer:
        return ProductOffer(
            source=source,
            title=title,
            url=f"https://example.com/{suffix}",
            price=price,
            currency="BYN",
            available=True,
        )

    def test_accumulates_deduplication_metrics(self) -> None:
        service = CatalogService()
        onliner = self.offer(
            "Onliner",
            "Apple iPhone 15 Pro 256GB Black Titanium",
            "iphone-onliner",
            1000,
        )
        twenty_one = self.offer(
            "21vek",
            "Apple iPhone 15 Pro 256 GB Black Titanium",
            "iphone-21vek",
            950,
        )

        service.ingest_offers((onliner, twenty_one))
        service.ingest_offer(
            self.offer(
                "onliner",
                onliner.title,
                "iphone-onliner",
                900,
            )
        )

        metrics = service.metrics
        self.assertEqual(metrics.batches, 2)
        self.assertEqual(metrics.total_offers, 3)
        self.assertEqual(metrics.created_products, 1)
        self.assertEqual(metrics.merged_offers, 1)
        self.assertEqual(metrics.updated_offers, 1)
        self.assertEqual(metrics.single_product_batches, 2)
        self.assertEqual(metrics.ambiguous_batches, 0)
        self.assertAlmostEqual(metrics.duplicate_rate, 2 / 3)
        self.assertEqual(metrics.presentation_eligibility_rate, 1.0)

    def test_tracks_ambiguous_and_empty_batches(self) -> None:
        service = CatalogService()

        service.ingest_offers(
            (
                self.offer(
                    "Onliner",
                    "Apple iPhone 15 Pro 256GB",
                    "iphone",
                    1000,
                ),
                self.offer(
                    "21vek",
                    "Samsung Galaxy S25 Ultra 256GB",
                    "samsung",
                    1200,
                ),
            )
        )
        service.ingest_offers(())

        metrics = service.metrics
        self.assertEqual(metrics.batches, 2)
        self.assertEqual(metrics.ambiguous_batches, 1)
        self.assertEqual(metrics.empty_batches, 1)
        self.assertEqual(metrics.single_product_batches, 0)
        self.assertEqual(metrics.presentation_eligibility_rate, 0.0)

    def test_tracks_master_product_lookup_hits_and_misses(self) -> None:
        service = CatalogService()
        product = service.ingest_offer(
            self.offer(
                "Onliner",
                "Bosch HBA534EB3",
                "bosch",
                1500,
            )
        )

        self.assertIsNotNone(service.get_product(product.key))
        self.assertIsNone(service.get_product("missing-product"))

        metrics = service.metrics
        self.assertEqual(metrics.lookup_hits, 1)
        self.assertEqual(metrics.lookup_misses, 1)

    def test_zero_denominators_are_safe(self) -> None:
        metrics = CatalogService().metrics

        self.assertEqual(metrics.duplicate_rate, 0.0)
        self.assertEqual(metrics.presentation_eligibility_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
