import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.models.catalog import (
    ExternalCatalogItem,
    MasterCatalogProduct,
    MatchLevel,
    ProductIdentity,
)
from app.services.catalog_service import CatalogService
from app.services.catalog_storage import JsonCatalogStorage
from app.services.sqlite_catalog_storage import SqliteCatalogStorage


class SqliteCatalogStorageTest(unittest.TestCase):
    @staticmethod
    def product(
        key: str = "product-1",
        source: str = "Onliner",
        external_id: str = "offer-1",
    ) -> MasterCatalogProduct:
        identity = ProductIdentity(
            brand="apple",
            model="iphone 17 pro",
            memory="256GB",
            color="black",
            ean="1234567890123",
        )
        return MasterCatalogProduct(
            key=key,
            title="Apple iPhone 17 Pro 256GB Black",
            identity=identity,
            offers=[
                ExternalCatalogItem(
                    source=source,
                    external_id=external_id,
                    title="Apple iPhone 17 Pro 256GB Black",
                    url=f"https://example.com/{external_id}",
                    price=3500.0,
                    currency="BYN",
                    available=True,
                    identity=identity,
                    match_level=MatchLevel.EXACT,
                    match_score=0.99,
                    match_reason="same_mpn",
                    match_conflicts=("revision",),
                    match_candidate_key=key,
                    updated_at=datetime(
                        2026,
                        7,
                        20,
                        12,
                        30,
                        tzinfo=timezone.utc,
                    ),
                )
            ],
        )

    def test_round_trip_preserves_catalog_and_match_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = SqliteCatalogStorage(
                Path(directory) / "catalog.sqlite3"
            )
            product = self.product()

            storage.save([product])
            restored = storage.load()

        self.assertEqual(storage.schema_version, 1)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].key, product.key)
        self.assertEqual(restored[0].identity, product.identity)
        self.assertEqual(len(restored[0].offers), 1)
        offer = restored[0].offers[0]
        self.assertEqual(offer.match_level, MatchLevel.EXACT)
        self.assertEqual(offer.match_score, 0.99)
        self.assertEqual(offer.match_reason, "same_mpn")
        self.assertEqual(offer.match_conflicts, ("revision",))
        self.assertEqual(offer.match_candidate_key, "product-1")
        self.assertEqual(offer.updated_at, product.offers[0].updated_at)

    def test_failed_snapshot_write_rolls_back_previous_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = SqliteCatalogStorage(
                Path(directory) / "catalog.sqlite3"
            )
            original = self.product()
            storage.save([original])
            conflicting = [
                self.product(key="product-2", source="Shop", external_id="same"),
                self.product(key="product-3", source="shop", external_id="same"),
            ]

            with self.assertRaises(sqlite3.IntegrityError):
                storage.save(conflicting)

            restored = storage.load()

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].key, original.key)

    def test_imports_json_only_when_database_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_storage = JsonCatalogStorage(root / "catalog.json")
            sqlite_storage = SqliteCatalogStorage(root / "catalog.sqlite3")
            json_storage.save([self.product()])

            imported = sqlite_storage.import_json_if_empty(json_storage)
            json_storage.save(
                [
                    self.product(),
                    self.product(
                        key="product-2",
                        source="21vek",
                        external_id="offer-2",
                    ),
                ]
            )
            repeated_import = sqlite_storage.import_json_if_empty(json_storage)

            restored = sqlite_storage.load()

        self.assertEqual(imported, 1)
        self.assertEqual(repeated_import, 0)
        self.assertEqual([product.key for product in restored], ["product-1"])

    def test_catalog_service_prefers_sqlite_and_migrates_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "catalog.json"
            database_path = root / "catalog.sqlite3"
            JsonCatalogStorage(json_path).save([self.product()])

            with patch.dict(
                os.environ,
                {
                    "CATALOG_DATABASE_PATH": str(database_path),
                    "CATALOG_STORAGE_PATH": str(json_path),
                },
                clear=False,
            ):
                service = CatalogService()
                restarted = CatalogService()

            self.assertEqual(service.storage_backend, "sqlite")
            self.assertEqual(service.storage_path, str(database_path))
            self.assertEqual(len(service.catalog.products), 1)
            self.assertEqual(len(restarted.catalog.products), 1)
            self.assertTrue(database_path.exists())
            self.assertEqual(
                SqliteCatalogStorage(database_path).schema_version,
                1,
            )


if __name__ == "__main__":
    unittest.main()
