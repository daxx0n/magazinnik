import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.offer import ProductOffer
from app.services.catalog_service import CatalogService


class CatalogEnvironmentTest(unittest.TestCase):
    @staticmethod
    def offer(price: float = 1200) -> ProductOffer:
        return ProductOffer(
            source="Onliner",
            title="Samsung Galaxy S25 Ultra 256GB",
            price=price,
            currency="BYN",
            available=True,
            url="https://example.com/s25-ultra",
        )

    def test_environment_path_persists_and_restores_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            with patch.dict(
                os.environ,
                {"CATALOG_STORAGE_PATH": str(path)},
                clear=False,
            ):
                first = CatalogService()
                first.ingest_offer(self.offer())
                restored = CatalogService()

            self.assertTrue(path.exists())
            self.assertEqual(len(restored.catalog.products), 1)
            self.assertEqual(restored.catalog.offer_count, 1)
            self.assertEqual(
                restored.catalog.products[0].offers[0].price,
                1200,
            )

    def test_corrupt_environment_snapshot_is_fail_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text("{broken", encoding="utf-8")

            with patch.dict(
                os.environ,
                {"CATALOG_STORAGE_PATH": str(path)},
                clear=False,
            ), self.assertLogs(
                "app.services.catalog_service",
                level="ERROR",
            ) as captured:
                service = CatalogService()

            self.assertEqual(service.catalog.products, ())
            self.assertTrue(
                any(
                    "Catalog snapshot restore failed" in message
                    for message in captured.output
                )
            )

    def test_empty_environment_path_keeps_catalog_in_memory(self) -> None:
        with patch.dict(
            os.environ,
            {"CATALOG_STORAGE_PATH": "   "},
            clear=False,
        ):
            service = CatalogService()
            service.ingest_offer(self.offer())

        self.assertEqual(len(service.catalog.products), 1)


if __name__ == "__main__":
    unittest.main()
