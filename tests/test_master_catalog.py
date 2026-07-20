import unittest

from app.models.catalog import (
    CatalogUpsertAction,
    ExternalCatalogItem,
)
from app.services.master_catalog import MasterCatalog
from app.services.product_identity import ProductIdentityBuilder


class MasterCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = MasterCatalog()
        self.builder = ProductIdentityBuilder()

    def item(
        self,
        source: str,
        external_id: str,
        title: str,
        price: float,
    ) -> ExternalCatalogItem:
        return ExternalCatalogItem(
            source=source,
            external_id=external_id,
            title=title,
            url=f"https://example.com/{source}/{external_id}",
            price=price,
            currency="BYN",
            identity=self.builder.build(title),
        )

    def test_merges_same_variant_from_different_sources(self) -> None:
        first = self.catalog.upsert(
            self.item(
                "Onliner",
                "iphone-15-pro-256-black",
                "Apple iPhone 15 Pro 256GB (черный титан)",
                4200,
            )
        )
        second = self.catalog.upsert(
            self.item(
                "21vek",
                "991",
                "Apple iPhone 15 Pro 256GB (Black Titanium)",
                4150,
            )
        )

        self.assertIs(first, second)
        self.assertEqual(len(self.catalog.products), 1)
        self.assertEqual(len(first.offers), 2)

    def test_keeps_different_memory_variants_separate(self) -> None:
        self.catalog.upsert(
            self.item(
                "Onliner",
                "iphone-256",
                "Apple iPhone 15 Pro 256GB (черный титан)",
                4200,
            )
        )
        self.catalog.upsert(
            self.item(
                "21vek",
                "iphone-512",
                "Apple iPhone 15 Pro 512GB (черный титан)",
                4700,
            )
        )

        self.assertEqual(len(self.catalog.products), 2)

    def test_repeated_import_updates_offer(self) -> None:
        product = self.catalog.upsert(
            self.item(
                "Onliner",
                "pixel-10",
                "Google Pixel 10 256GB (Obsidian)",
                3000,
            )
        )
        updated = self.catalog.upsert(
            self.item(
                "onliner",
                "pixel-10",
                "Google Pixel 10 256GB (Obsidian)",
                2899,
            )
        )

        self.assertIs(product, updated)
        self.assertEqual(len(product.offers), 1)
        self.assertEqual(product.offers[0].price, 2899)

    def test_reports_created_merged_and_updated_actions(self) -> None:
        created = self.catalog.upsert_with_result(
            self.item(
                "Onliner",
                "iphone-onliner",
                "Apple iPhone 15 Pro 256GB Black Titanium",
                4200,
            )
        )
        merged = self.catalog.upsert_with_result(
            self.item(
                "21vek",
                "iphone-21vek",
                "Apple iPhone 15 Pro 256 GB Black Titanium",
                4100,
            )
        )
        updated = self.catalog.upsert_with_result(
            self.item(
                "onliner",
                "iphone-onliner",
                "Apple iPhone 15 Pro 256GB Black Titanium",
                4000,
            )
        )

        self.assertEqual(created.action, CatalogUpsertAction.CREATED)
        self.assertEqual(merged.action, CatalogUpsertAction.MERGED)
        self.assertEqual(updated.action, CatalogUpsertAction.UPDATED)
        self.assertIs(created.product, merged.product)
        self.assertIs(created.product, updated.product)

    def test_restore_rebuilds_indexes_and_key_sequence(self) -> None:
        original = MasterCatalog()
        product = original.upsert(
            self.item(
                "Onliner",
                "pixel-10",
                "Google Pixel 10 256GB Obsidian",
                3000,
            )
        )

        restored = MasterCatalog()
        restored.restore(original.products)
        update_result = restored.upsert_with_result(
            self.item(
                "onliner",
                "pixel-10",
                "Google Pixel 10 256GB Obsidian",
                2899,
            )
        )
        new_product = restored.upsert(
            self.item(
                "21vek",
                "bosch-oven",
                "Bosch HBA534EB3",
                1800,
            )
        )

        self.assertEqual(update_result.action, CatalogUpsertAction.UPDATED)
        self.assertIs(update_result.product, product)
        self.assertEqual(update_result.product.offers[0].price, 2899)
        self.assertEqual(new_product.key, "product-2")
        self.assertEqual(restored.offer_count, 2)

    def test_searches_master_and_source_titles(self) -> None:
        product = self.catalog.upsert(
            self.item(
                "Onliner",
                "s25",
                "Samsung Galaxy S25 12GB/256GB (синий)",
                2800,
            )
        )

        self.assertEqual(self.catalog.search("galaxy s25"), [product])
        self.assertEqual(self.catalog.search("Samsung Galaxy"), [product])

    def test_requires_identity_for_new_product(self) -> None:
        item = ExternalCatalogItem(
            source="Unknown",
            external_id="1",
            title="Unknown product",
            url="https://example.com/1",
        )

        with self.assertRaises(ValueError):
            self.catalog.upsert(item)


if __name__ == "__main__":
    unittest.main()
