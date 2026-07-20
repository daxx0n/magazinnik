import gc
import tempfile
import unittest
import warnings
from pathlib import Path

from app.services.price_history import PriceHistoryRepository
from app.services.sqlite_catalog_storage import SqliteCatalogStorage


class SqliteResourceSafetyTest(unittest.TestCase):
    def test_repeated_catalog_reads_do_not_leak_connections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = SqliteCatalogStorage(
                Path(directory) / "catalog.sqlite3"
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                for _ in range(50):
                    self.assertEqual(storage.schema_version, 1)
                    self.assertTrue(storage.is_empty())
                    self.assertEqual(storage.load(), [])
                gc.collect()

            resource_warnings = [
                warning
                for warning in caught
                if issubclass(warning.category, ResourceWarning)
            ]
            self.assertEqual(resource_warnings, [])

    def test_repeated_price_history_reads_do_not_leak_connections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = PriceHistoryRepository(
                Path(directory) / "prices.sqlite3"
            )
            repository.initialize()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                for _ in range(100):
                    self.assertEqual(repository.history("missing"), [])
                    self.assertEqual(repository.active_alerts(), [])
                gc.collect()

            resource_warnings = [
                warning
                for warning in caught
                if issubclass(warning.category, ResourceWarning)
            ]
            self.assertEqual(resource_warnings, [])


if __name__ == "__main__":
    unittest.main()
