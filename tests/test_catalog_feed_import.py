import json
import unittest

from app.services.catalog_feed_import import CatalogFeedImporter
from app.services.catalog_service import CatalogService
from app.services.master_catalog import MasterCatalog


class CatalogFeedImportTest(unittest.TestCase):
    def build_importer(self) -> tuple[CatalogFeedImporter, CatalogService]:
        service = CatalogService(
            catalog=MasterCatalog(),
            restore_on_start=False,
        )
        return CatalogFeedImporter(service), service

    @staticmethod
    def feed() -> str:
        return json.dumps(
            [
                {
                    "source": "Onliner",
                    "external_id": "pixel-onliner",
                    "title": "Google Pixel 8 8GB/128GB (Obsidian)",
                    "url": "https://example.com/onliner/pixel-8",
                    "price": "2099,00",
                    "currency": "byn",
                    "available": True,
                    "identity": {
                        "brand": "Google",
                        "model": "Pixel 8",
                        "memory": "8GB/128GB",
                        "color": "Obsidian",
                        "ean": "0840244700001",
                        "mpn": "GA04803-US",
                    },
                },
                {
                    "source": "Shop.by",
                    "sku": "pixel-shopby",
                    "title": "Смартфон Google Pixel 8 8/128GB черный",
                    "url": "https://example.com/shopby/pixel-8",
                    "price": 1899,
                    "available": "in_stock",
                    "brand": "Google",
                    "model": "Pixel 8",
                    "memory": "8/128GB",
                    "color": "black",
                    "gtin": "0840244700001",
                },
            ],
            ensure_ascii=False,
        )

    def test_imports_and_merges_records_by_ean(self) -> None:
        importer, service = self.build_importer()

        report = importer.import_text(self.feed(), format_hint="json")

        self.assertEqual(report.status, "imported")
        self.assertEqual(report.total_records, 2)
        self.assertEqual(report.valid_records, 2)
        self.assertEqual(report.invalid_records, 0)
        self.assertEqual(report.created_products, 1)
        self.assertEqual(report.merged_offers, 1)
        self.assertEqual(len(service.catalog.products), 1)
        product = service.catalog.products[0]
        self.assertEqual(len(product.offers), 2)
        self.assertEqual(product.identity.ean, "0840244700001")
        self.assertEqual(product.identity.mpn, "ga04803us")
        self.assertEqual(product.identity.memory, "8GB/128GB")

    def test_repeated_import_updates_without_duplicates(self) -> None:
        importer, service = self.build_importer()
        importer.import_text(self.feed())

        report = importer.import_text(self.feed())

        self.assertEqual(report.created_products, 0)
        self.assertEqual(report.merged_offers, 0)
        self.assertEqual(report.updated_offers, 2)
        self.assertEqual(len(service.catalog.products), 1)
        self.assertEqual(len(service.catalog.products[0].offers), 2)

    def test_dry_run_reports_actions_without_mutating_catalog(self) -> None:
        importer, service = self.build_importer()

        report = importer.import_text(self.feed(), dry_run=True)

        self.assertEqual(report.status, "dry_run")
        self.assertEqual(report.created_products, 1)
        self.assertEqual(report.merged_offers, 1)
        self.assertEqual(service.catalog.products, ())

    def test_rejects_whole_jsonl_feed_by_default(self) -> None:
        importer, service = self.build_importer()
        text = "\n".join(
            [
                json.dumps(
                    {
                        "source": "Onliner",
                        "title": "Google Pixel 8",
                        "url": "https://example.com/pixel-8",
                        "price": 1000,
                    }
                ),
                "{broken json",
            ]
        )

        report = importer.import_text(text, format_hint="jsonl")

        self.assertEqual(report.status, "rejected")
        self.assertEqual(report.total_records, 2)
        self.assertEqual(report.valid_records, 1)
        self.assertEqual(report.invalid_records, 1)
        self.assertEqual(service.catalog.products, ())

    def test_partial_mode_imports_valid_jsonl_records(self) -> None:
        importer, service = self.build_importer()
        text = "\n".join(
            [
                json.dumps(
                    {
                        "title": "Google Pixel 8",
                        "url": "https://example.com/pixel-8",
                        "price": 1000,
                    }
                ),
                "{broken json",
            ]
        )

        report = importer.import_text(
            text,
            format_hint="jsonl",
            allow_partial=True,
            default_source="Supplier feed",
        )

        self.assertEqual(report.status, "imported")
        self.assertEqual(report.valid_records, 1)
        self.assertEqual(report.invalid_records, 1)
        self.assertEqual(len(service.catalog.products), 1)
        offer = service.catalog.products[0].offers[0]
        self.assertEqual(offer.source, "Supplier feed")
        self.assertEqual(len(offer.external_id), 24)

    def test_invalid_field_types_are_reported_not_raised(self) -> None:
        importer, service = self.build_importer()
        text = json.dumps(
            [
                {
                    "source": "Feed",
                    "title": "Google Pixel 8",
                    "url": "not-a-url",
                    "price": {"value": 1000},
                    "available": "maybe",
                    "updated_at": ["2026-07-20"],
                }
            ]
        )

        report = importer.import_text(text)

        self.assertEqual(report.status, "rejected")
        self.assertEqual(report.invalid_records, 1)
        fields = {issue.field for issue in report.issues}
        self.assertTrue({"url", "price", "available", "updated_at"}.issubset(fields))
        self.assertEqual(service.catalog.products, ())

    def test_supports_items_wrapper_and_single_object(self) -> None:
        importer, _ = self.build_importer()
        record = {
            "source": "Feed",
            "title": "Bosch HBA534EB3",
            "url": "https://example.com/bosch",
        }

        wrapped = importer.import_text(json.dumps({"items": [record]}), dry_run=True)
        single = importer.import_text(json.dumps(record), dry_run=True)

        self.assertEqual(wrapped.valid_records, 1)
        self.assertEqual(single.valid_records, 1)


if __name__ == "__main__":
    unittest.main()
