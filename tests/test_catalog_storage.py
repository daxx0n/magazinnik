import tempfile
import unittest
from pathlib import Path

from app.models.catalog import (
    ExternalCatalogItem,
    MasterCatalogProduct,
    ProductIdentity,
)
from app.services.catalog_storage import JsonCatalogStorage


class JsonCatalogStorageTest(unittest.TestCase):
    def test_round_trip_preserves_product_and_offer(self) -> None:
        identity = ProductIdentity(
            brand="apple",
            model="iphone 15 pro",
            memory="256GB",
            color="black_titanium",
        )
        product = MasterCatalogProduct(
            key="apple-iphone-15-pro-256-black",
            title="Apple iPhone 15 Pro 256GB",
            identity=identity,
            offers=[
                ExternalCatalogItem(
                    source="Shop",
                    external_id="42",
                    title="Apple iPhone 15 Pro 256GB",
                    url="https://example.com/42",
                    price=3000.0,
                    currency="BYN",
                    identity=identity,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as directory:
            storage = JsonCatalogStorage(Path(directory) / "catalog.json")
            storage.save([product])
            restored = storage.load()

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].identity, identity)
        self.assertEqual(restored[0].offers[0].external_id, "42")
        self.assertEqual(restored[0].offers[0].price, 3000.0)

    def test_missing_snapshot_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = JsonCatalogStorage(Path(directory) / "missing.json")
            self.assertEqual(storage.load(), [])

    def test_rejects_non_list_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text("{}", encoding="utf-8")
            storage = JsonCatalogStorage(path)
            with self.assertRaises(ValueError):
                storage.load()


if __name__ == "__main__":
    unittest.main()
