import json
import unittest
from pathlib import Path

from app.services.catalog_feed_import import CatalogFeedImporter
from app.services.catalog_service import CatalogService
from app.services.master_catalog import MasterCatalog


class FailingStorage:
    path = Path("failing-catalog")

    def save(self, products) -> None:
        raise RuntimeError("storage failed")

    def load(self):
        return []


class CatalogFeedSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CatalogService(
            catalog=MasterCatalog(),
            restore_on_start=False,
        )
        self.importer = CatalogFeedImporter(self.service)
        self.importer.import_text(
            json.dumps(
                [
                    self.record(
                        source="Supplier A",
                        external_id="pixel-8",
                        title="Google Pixel 8 128GB",
                        url="https://a.example/pixel-8",
                        ean="0840244700001",
                    ),
                    self.record(
                        source="Supplier A",
                        external_id="pixel-9",
                        title="Google Pixel 9 128GB",
                        url="https://a.example/pixel-9",
                        ean="0840244700002",
                    ),
                    self.record(
                        source="Other Shop",
                        external_id="iphone-17",
                        title="Apple iPhone 17 256GB",
                        url="https://other.example/iphone-17",
                        ean="0195950000001",
                    ),
                ]
            )
        )

    @staticmethod
    def record(
        *,
        source: str,
        external_id: str,
        title: str,
        url: str,
        ean: str,
        price: float = 1000,
    ) -> dict:
        return {
            "source": source,
            "external_id": external_id,
            "title": title,
            "url": url,
            "price": price,
            "available": True,
            "ean": ean,
        }

    def snapshot_text(self) -> str:
        return json.dumps(
            [
                self.record(
                    source="Supplier A",
                    external_id="pixel-8",
                    title="Google Pixel 8 128GB",
                    url="https://a.example/pixel-8",
                    ean="0840244700001",
                    price=900,
                )
            ]
        )

    def offers(self) -> dict[tuple[str, str], object]:
        return {
            (offer.source, offer.external_id): offer
            for product in self.service.catalog.products
            for offer in product.offers
        }

    def test_dry_run_reports_deactivation_without_mutation(self) -> None:
        before = self.offers()
        old_pixel_9_time = before[("Supplier A", "pixel-9")].updated_at

        report = self.importer.import_text(
            self.snapshot_text(),
            dry_run=True,
            snapshot=True,
        )

        self.assertEqual(report.status, "dry_run")
        self.assertEqual(report.updated_offers, 1)
        self.assertEqual(report.deactivated_offers, 1)
        after = self.offers()
        self.assertTrue(after[("Supplier A", "pixel-9")].available)
        self.assertEqual(
            after[("Supplier A", "pixel-9")].updated_at,
            old_pixel_9_time,
        )

    def test_snapshot_deactivates_only_missing_offers_of_its_source(self) -> None:
        report = self.importer.import_text(
            self.snapshot_text(),
            snapshot=True,
        )

        self.assertEqual(report.status, "imported")
        self.assertEqual(report.updated_offers, 1)
        self.assertEqual(report.deactivated_offers, 1)
        offers = self.offers()
        self.assertTrue(offers[("Supplier A", "pixel-8")].available)
        self.assertFalse(offers[("Supplier A", "pixel-9")].available)
        self.assertTrue(offers[("Other Shop", "iphone-17")].available)
        self.assertEqual(offers[("Supplier A", "pixel-8")].price, 900)

    def test_repeated_snapshot_is_idempotent(self) -> None:
        first = self.importer.import_text(
            self.snapshot_text(),
            snapshot=True,
        )
        second = self.importer.import_text(
            self.snapshot_text(),
            snapshot=True,
        )

        self.assertEqual(first.deactivated_offers, 1)
        self.assertEqual(second.deactivated_offers, 0)
        self.assertEqual(second.updated_offers, 1)

    def test_snapshot_rejects_multiple_sources(self) -> None:
        text = json.dumps(
            [
                self.record(
                    source="Supplier A",
                    external_id="pixel-8",
                    title="Google Pixel 8",
                    url="https://a.example/pixel-8",
                    ean="0840244700001",
                ),
                self.record(
                    source="Supplier B",
                    external_id="pixel-9",
                    title="Google Pixel 9",
                    url="https://b.example/pixel-9",
                    ean="0840244700002",
                ),
            ]
        )

        report = self.importer.import_text(text, snapshot=True)

        self.assertEqual(report.status, "rejected")
        self.assertEqual(report.deactivated_offers, 0)
        self.assertIn("source", {issue.field for issue in report.issues})
        self.assertTrue(self.offers()[("Supplier A", "pixel-9")].available)

    def test_snapshot_rejects_invalid_or_empty_feed(self) -> None:
        invalid = self.importer.import_text(
            json.dumps(
                [
                    {
                        "source": "Supplier A",
                        "title": "Broken",
                        "url": "not-a-url",
                    }
                ]
            ),
            snapshot=True,
        )
        empty = self.importer.import_text("[]", snapshot=True)

        self.assertEqual(invalid.status, "rejected")
        self.assertEqual(empty.status, "rejected")
        self.assertTrue(self.offers()[("Supplier A", "pixel-9")].available)

    def test_snapshot_cannot_use_partial_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "partial"):
            self.importer.import_text(
                self.snapshot_text(),
                snapshot=True,
                allow_partial=True,
            )

    def test_storage_failure_rolls_back_updates_and_deactivations(self) -> None:
        offers_before = self.offers()
        old_price = offers_before[("Supplier A", "pixel-8")].price
        self.service._storage = FailingStorage()

        with self.assertRaisesRegex(RuntimeError, "storage failed"):
            self.importer.import_text(
                self.snapshot_text(),
                snapshot=True,
            )

        offers_after = self.offers()
        self.assertEqual(
            offers_after[("Supplier A", "pixel-8")].price,
            old_price,
        )
        self.assertTrue(offers_after[("Supplier A", "pixel-9")].available)


if __name__ == "__main__":
    unittest.main()
