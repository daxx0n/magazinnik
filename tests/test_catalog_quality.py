import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.handlers.catalog import (
    format_catalog_reviews,
    format_catalog_stats,
)
from app.models.catalog import (
    CatalogSnapshotMetrics,
    CatalogUpsertAction,
    ExternalCatalogItem,
    MatchLevel,
    ProductIdentity,
)
from app.models.catalog_metrics import CatalogMetrics
from app.services.catalog_service import CatalogService
from app.services.catalog_storage import JsonCatalogStorage
from app.services.master_catalog import MasterCatalog


class CatalogQualityTest(unittest.TestCase):
    @staticmethod
    def item(
        source: str,
        external_id: str,
        title: str,
        identity: ProductIdentity,
        updated_at: datetime | None = None,
        available: bool = True,
    ) -> ExternalCatalogItem:
        return ExternalCatalogItem(
            source=source,
            external_id=external_id,
            title=title,
            url=f"https://example.com/{external_id}",
            price=1000.0,
            currency="BYN",
            available=available,
            identity=identity,
            updated_at=updated_at or datetime.now(timezone.utc),
        )

    def build_review_catalog(
        self,
    ) -> tuple[MasterCatalog, str, str]:
        catalog = MasterCatalog()
        candidate = catalog.upsert(
            self.item(
                "Onliner",
                "one",
                "Apple iPhone 17",
                ProductIdentity(brand="apple", model="iphone 17"),
            )
        )
        product = catalog.upsert(
            self.item(
                "21vek",
                "two",
                "Aple iPhone 17",
                ProductIdentity(brand="aple", model="iphone 17"),
            )
        )
        return catalog, product.key, candidate.key

    def test_exact_merge_stores_reason_and_confidence(self) -> None:
        catalog = MasterCatalog()
        identity = ProductIdentity(
            brand="apple",
            model="iphone 17 pro",
            memory="256GB",
            ean="1234567890123",
        )
        catalog.upsert_with_result(
            self.item("Onliner", "one", "Apple iPhone 17 Pro", identity)
        )

        result = catalog.upsert_with_result(
            self.item("21vek", "two", "iPhone 17 Pro", identity)
        )

        self.assertEqual(result.action, CatalogUpsertAction.MERGED)
        merged_offer = result.product.offers[-1]
        self.assertEqual(merged_offer.match_level, MatchLevel.EXACT)
        self.assertEqual(merged_offer.match_reason, "same_ean")
        self.assertEqual(merged_offer.match_score, 1.0)
        self.assertEqual(
            merged_offer.match_candidate_key,
            result.product.key,
        )

    def test_review_match_creates_separate_product_and_queue_item(self) -> None:
        catalog, product_key, candidate_key = self.build_review_catalog()

        reviews = catalog.pending_reviews()
        self.assertEqual(len(catalog.products), 2)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].product_key, product_key)
        self.assertEqual(reviews[0].candidate_product_key, candidate_key)
        self.assertEqual(
            reviews[0].reason,
            "ambiguous_brand_or_model",
        )
        self.assertGreater(reviews[0].score, 0.9)

    def test_review_queue_survives_json_round_trip(self) -> None:
        catalog, _, _ = self.build_review_catalog()

        with tempfile.TemporaryDirectory() as directory:
            storage = JsonCatalogStorage(Path(directory) / "catalog.json")
            storage.save(catalog.products)
            restored = MasterCatalog()
            restored.restore(storage.load())

        reviews = restored.pending_reviews()
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].source, "21vek")
        self.assertEqual(reviews[0].score, catalog.pending_reviews()[0].score)

    def test_accept_review_merges_products_and_reindexes_offers(self) -> None:
        catalog, product_key, candidate_key = self.build_review_catalog()

        merged = catalog.accept_review(product_key, candidate_key)

        self.assertEqual(merged.key, candidate_key)
        self.assertEqual(len(catalog.products), 1)
        self.assertEqual(len(merged.offers), 2)
        self.assertEqual(catalog.pending_reviews(), ())
        moved_offer = next(
            offer for offer in merged.offers if offer.external_id == "two"
        )
        self.assertEqual(moved_offer.match_level, MatchLevel.PROBABLE)
        self.assertEqual(moved_offer.match_reason, "manual_approval")

        updated = catalog.upsert_with_result(
            self.item(
                "21vek",
                "two",
                "Aple iPhone 17",
                ProductIdentity(brand="aple", model="iphone 17"),
            )
        )
        self.assertEqual(updated.action, CatalogUpsertAction.UPDATED)
        self.assertEqual(updated.product.key, candidate_key)

    def test_reject_review_keeps_products_separate(self) -> None:
        catalog, product_key, candidate_key = self.build_review_catalog()

        product = catalog.reject_review(product_key, candidate_key)

        self.assertEqual(len(catalog.products), 2)
        self.assertEqual(catalog.pending_reviews(), ())
        self.assertEqual(product.offers[0].match_level, MatchLevel.REJECTED)
        self.assertEqual(product.offers[0].match_reason, "manual_rejection")
        metrics = catalog.metrics()
        self.assertEqual(metrics.review_matches, 0)
        self.assertEqual(metrics.rejected_matches, 1)

    def test_service_persists_accepted_review(self) -> None:
        catalog, product_key, candidate_key = self.build_review_catalog()

        with tempfile.TemporaryDirectory() as directory:
            storage = JsonCatalogStorage(Path(directory) / "catalog.json")
            service = CatalogService(
                catalog=catalog,
                storage=storage,
                restore_on_start=False,
            )
            service.accept_review(product_key, candidate_key)
            restored = CatalogService(storage=storage)

        self.assertEqual(len(restored.catalog.products), 1)
        self.assertEqual(restored.pending_reviews(), ())
        self.assertEqual(len(restored.catalog.products[0].offers), 2)

    def test_snapshot_metrics_cover_deduplication_and_freshness(self) -> None:
        now = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
        catalog = MasterCatalog()
        identity = ProductIdentity(
            brand="apple",
            model="iphone 17 pro",
            memory="256GB",
            ean="1234567890123",
        )
        catalog.upsert(
            self.item(
                "Onliner",
                "one",
                "Apple iPhone 17 Pro",
                identity,
                updated_at=now - timedelta(hours=30),
            )
        )
        catalog.upsert(
            self.item(
                "21vek",
                "two",
                "Apple iPhone 17 Pro",
                identity,
                updated_at=now - timedelta(hours=2),
            )
        )
        catalog.upsert(
            self.item(
                "Shop.by",
                "three",
                "Aple iPhone 17 Pro",
                ProductIdentity(brand="aple", model="iphone 17 pro"),
                updated_at=now - timedelta(hours=1),
                available=False,
            )
        )

        metrics = catalog.metrics(now=now)

        self.assertEqual(metrics.product_count, 2)
        self.assertEqual(metrics.offer_count, 3)
        self.assertEqual(metrics.merged_offer_count, 1)
        self.assertAlmostEqual(metrics.duplicate_rate, 1 / 3)
        self.assertEqual(metrics.multi_source_products, 1)
        self.assertEqual(metrics.single_source_products, 1)
        self.assertEqual(metrics.exact_matches, 1)
        self.assertEqual(metrics.review_matches, 1)
        self.assertEqual(metrics.fresh_offers, 2)
        self.assertEqual(metrics.stale_offers, 1)
        self.assertEqual(metrics.unavailable_offers, 1)
        self.assertEqual(
            metrics.source_offer_counts,
            (("21vek", 1), ("Onliner", 1), ("Shop.by", 1)),
        )

    def test_formats_admin_quality_reports(self) -> None:
        snapshot = CatalogSnapshotMetrics(
            product_count=2,
            offer_count=3,
            merged_offer_count=1,
            duplicate_rate=1 / 3,
            single_source_products=1,
            multi_source_products=1,
            exact_matches=1,
            probable_matches=0,
            review_matches=1,
            rejected_matches=0,
            fresh_offers=2,
            stale_offers=1,
            unavailable_offers=0,
            source_offer_counts=(("Onliner", 2), ("21vek", 1)),
        )
        runtime = CatalogMetrics(
            batches=4,
            single_product_batches=3,
            ambiguous_batches=1,
        )

        text = format_catalog_stats(snapshot, runtime)

        self.assertIn("Карточек: 2", text)
        self.assertIn("Объединённых офферов: 1 (33.3%)", text)
        self.assertIn("review: 1", text)
        self.assertIn("пригодность мастер-представления: 75.0%", text)
        self.assertIn("Onliner: 2", text)

        catalog, _, _ = self.build_review_catalog()
        review_text = format_catalog_reviews(
            catalog.pending_reviews(),
            total=1,
        )
        self.assertIn("/catalog_review_accept", review_text)
        self.assertIn("/catalog_review_reject", review_text)


if __name__ == "__main__":
    unittest.main()
