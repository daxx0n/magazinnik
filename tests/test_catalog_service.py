import tempfile
import unittest
from pathlib import Path

from app.models.offer import ProductOffer
from app.services.catalog_service import CatalogService
from app.services.catalog_storage import JsonCatalogStorage


class CatalogServiceTest(unittest.TestCase):
    @staticmethod
    def offer(
        source: str,
        title: str,
        url: str,
        price: float,
    ) -> ProductOffer:
        return ProductOffer(
            source=source,
            title=title,
            url=url,
            price=price,
            currency="BYN",
            available=True,
        )

    def test_ingests_offers_into_master_catalog(self) -> None:
        service = CatalogService()
        first = self.offer(
            source="Onliner",
            title="Apple iPhone 15 Pro 256GB Black Titanium",
            url="https://example.com/iphone",
            price=1000,
        )
        second = self.offer(
            source="21vek",
            title="Apple iPhone 15 Pro 256 GB Black Titanium",
            url="https://example.com/iphone-2",
            price=950,
        )

        products = service.ingest_offers((first, second))

        self.assertEqual(len(products), 2)
        self.assertEqual(len(service.catalog.products), 1)
        self.assertEqual(len(service.catalog.products[0].offers), 2)

    def test_reports_batch_deduplication_actions(self) -> None:
        service = CatalogService()
        first = self.offer(
            source="Onliner",
            title="Apple iPhone 15 Pro 256GB Black Titanium",
            url="https://example.com/iphone",
            price=1000,
        )
        second = self.offer(
            source="21vek",
            title="Apple iPhone 15 Pro 256 GB Black Titanium",
            url="https://example.com/iphone-2",
            price=950,
        )

        report = service.ingest_offers_with_report((first, second))
        update_report = service.ingest_offers_with_report(
            (
                self.offer(
                    source="onliner",
                    title=first.title,
                    url=first.url,
                    price=900,
                ),
            )
        )

        self.assertEqual(report.total_offers, 2)
        self.assertEqual(report.created_products, 1)
        self.assertEqual(report.merged_offers, 1)
        self.assertEqual(report.updated_offers, 0)
        self.assertEqual(len(report.product_keys), 1)
        self.assertEqual(update_report.updated_offers, 1)
        self.assertEqual(
            service.catalog.products[0].offers[0].price,
            900,
        )

    def test_restores_catalog_from_persisted_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = JsonCatalogStorage(
                Path(directory) / "catalog.json"
            )
            service = CatalogService(storage=storage)
            service.ingest_offers(
                (
                    self.offer(
                        source="Onliner",
                        title="Samsung Galaxy S25 Ultra 256GB",
                        url="https://example.com/samsung",
                        price=1200,
                    ),
                    self.offer(
                        source="21vek",
                        title="Samsung Galaxy S25 Ultra 256 GB",
                        url="https://example.com/samsung-2",
                        price=1150,
                    ),
                )
            )

            restored = CatalogService(storage=storage)
            update_report = restored.ingest_offers_with_report(
                (
                    self.offer(
                        source="onliner",
                        title="Samsung Galaxy S25 Ultra 256GB",
                        url="https://example.com/samsung",
                        price=1100,
                    ),
                )
            )

        self.assertEqual(len(restored.catalog.products), 1)
        self.assertEqual(restored.catalog.offer_count, 2)
        self.assertEqual(update_report.updated_offers, 1)
        self.assertEqual(len(restored.search("Galaxy S25")), 1)

    def test_searches_master_catalog(self) -> None:
        service = CatalogService()
        service.ingest_offer(
            self.offer(
                source="Onliner",
                title="Samsung Galaxy S25 Ultra 256GB",
                url="https://example.com/samsung",
                price=1200,
            )
        )

        result = service.search("Galaxy S25")

        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
