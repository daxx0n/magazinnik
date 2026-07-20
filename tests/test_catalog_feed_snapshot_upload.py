import json
import unittest

from app.handlers.catalog_feed import (
    format_catalog_feed_report,
    parse_catalog_feed_request,
)
from app.services.catalog_feed_import import CatalogFeedImporter
from app.services.catalog_feed_upload import CatalogFeedUploadManager
from app.services.catalog_service import CatalogService
from app.services.master_catalog import MasterCatalog


class CatalogFeedSnapshotUploadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CatalogService(
            catalog=MasterCatalog(),
            restore_on_start=False,
        )
        CatalogFeedImporter(self.service).import_text(
            json.dumps(
                [
                    self.record("one", "Google Pixel 8"),
                    self.record("two", "Google Pixel 9"),
                ]
            )
        )
        self.manager = CatalogFeedUploadManager(self.service)

    @staticmethod
    def record(external_id: str, title: str) -> dict:
        return {
            "source": "Supplier A",
            "external_id": external_id,
            "title": title,
            "url": f"https://example.com/{external_id}",
            "price": 1000,
        }

    def available(self, external_id: str) -> bool:
        return next(
            offer.available
            for product in self.service.catalog.products
            for offer in product.offers
            if offer.external_id == external_id
        )

    def test_snapshot_session_preserves_mode_until_confirmation(self) -> None:
        text = json.dumps([self.record("one", "Google Pixel 8")])

        session, dry_run = self.manager.prepare(
            chat_id=1,
            user_id=2,
            filename="snapshot.json",
            text=text,
            snapshot=True,
        )

        assert session is not None
        self.assertTrue(session.snapshot)
        self.assertEqual(dry_run.deactivated_offers, 1)
        self.assertTrue(self.available("two"))

        report = self.manager.confirm(
            session.token,
            chat_id=1,
            user_id=2,
        )

        self.assertEqual(report.deactivated_offers, 1)
        self.assertFalse(self.available("two"))

    def test_snapshot_caption_and_report_are_explicit(self) -> None:
        request = parse_catalog_feed_request(
            "/catalog_feed_snapshot Supplier A"
        )
        assert request is not None
        self.assertTrue(request.snapshot)
        self.assertEqual(request.default_source, "Supplier A")

        session, report = self.manager.prepare(
            chat_id=1,
            user_id=2,
            filename="snapshot.json",
            text=json.dumps([self.record("one", "Google Pixel 8")]),
            snapshot=True,
        )
        assert session is not None
        text = format_catalog_feed_report(report, title="Snapshot")
        self.assertIn("Станут недоступными: 1", text)


if __name__ == "__main__":
    unittest.main()
