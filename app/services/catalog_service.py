import logging
import os
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timedelta

from app.models.catalog import (
    CatalogIngestReport,
    CatalogSnapshotMetrics,
    CatalogUpsertAction,
    CatalogUpsertResult,
    MasterCatalogProduct,
    MatchReview,
)
from app.models.catalog_metrics import CatalogMetrics
from app.models.offer import ProductOffer
from app.services.catalog_adapter import CatalogOfferAdapter
from app.services.catalog_storage import JsonCatalogStorage
from app.services.master_catalog import MasterCatalog
from app.services.sqlite_catalog_storage import SqliteCatalogStorage


logger = logging.getLogger(__name__)


CatalogStorage = JsonCatalogStorage | SqliteCatalogStorage


class CatalogService:
    """Координирует адаптацию, дедупликацию и сохранение офферов."""

    _storage_path_env = "CATALOG_STORAGE_PATH"
    _database_path_env = "CATALOG_DATABASE_PATH"

    def __init__(
        self,
        catalog: MasterCatalog | None = None,
        adapter: CatalogOfferAdapter | None = None,
        storage: CatalogStorage | None = None,
        restore_on_start: bool = True,
    ) -> None:
        self._catalog = catalog or MasterCatalog()
        self._adapter = adapter or CatalogOfferAdapter()
        self._storage = storage or self._storage_from_environment()
        self._last_report = CatalogIngestReport(
            total_offers=0,
            created_products=0,
            merged_offers=0,
            updated_offers=0,
        )
        self._metrics = CatalogMetrics()

        if self._storage is not None and restore_on_start:
            self._restore_fail_open()

    @property
    def catalog(self) -> MasterCatalog:
        return self._catalog

    @property
    def last_report(self) -> CatalogIngestReport:
        return self._last_report

    @property
    def metrics(self) -> CatalogMetrics:
        """Возвращает неизменяемый снимок накопленных метрик."""

        return self._metrics

    @property
    def storage_path(self) -> str | None:
        """Возвращает активный путь постоянного хранилища."""

        return str(self._storage.path) if self._storage is not None else None

    @property
    def storage_backend(self) -> str:
        """Показывает выбранный backend для диагностики."""

        if isinstance(self._storage, SqliteCatalogStorage):
            return "sqlite"
        if isinstance(self._storage, JsonCatalogStorage):
            return "json"
        return "memory"

    def ingest_offer(self, offer: ProductOffer) -> MasterCatalogProduct:
        result = self._ingest(offer)
        self._last_report = self._build_report((result,))
        self._record_report(self._last_report)
        self._persist()
        return result.product

    def ingest_offers(
        self,
        offers: Iterable[ProductOffer],
    ) -> tuple[MasterCatalogProduct, ...]:
        results = tuple(self._ingest(offer) for offer in offers)
        self._last_report = self._build_report(results)
        self._record_report(self._last_report)
        self._persist()
        return tuple(result.product for result in results)

    def ingest_offers_with_report(
        self,
        offers: Iterable[ProductOffer],
    ) -> CatalogIngestReport:
        self.ingest_offers(offers)
        return self._last_report

    def search(self, query: str) -> list[MasterCatalogProduct]:
        return self._catalog.search(query)

    def get_product(
        self,
        product_key: str,
    ) -> MasterCatalogProduct | None:
        """Возвращает мастер-карточку по стабильному ключу."""

        product = next(
            (
                item
                for item in self._catalog.products
                if item.key == product_key
            ),
            None,
        )
        self._metrics = replace(
            self._metrics,
            lookup_hits=(
                self._metrics.lookup_hits + int(product is not None)
            ),
            lookup_misses=(
                self._metrics.lookup_misses + int(product is None)
            ),
        )
        return product

    def snapshot_metrics(
        self,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(hours=24),
    ) -> CatalogSnapshotMetrics:
        """Возвращает метрики текущего сохранённого состояния каталога."""

        return self._catalog.metrics(
            now=now,
            stale_after=stale_after,
        )

    def pending_reviews(self, limit: int = 20) -> tuple[MatchReview, ...]:
        """Возвращает спорные пары, сохранённые вместе с офферами."""

        return self._catalog.pending_reviews(limit=limit)

    def accept_review(
        self,
        product_key: str,
        candidate_product_key: str,
    ) -> MasterCatalogProduct:
        """Подтверждает объединение спорной мастер-карточки."""

        product = self._catalog.accept_review(
            product_key,
            candidate_product_key,
        )
        self._persist()
        return product

    def reject_review(
        self,
        product_key: str,
        candidate_product_key: str,
    ) -> MasterCatalogProduct:
        """Подтверждает, что спорные карточки являются разными."""

        product = self._catalog.reject_review(
            product_key,
            candidate_product_key,
        )
        self._persist()
        return product

    def save(self) -> None:
        """Принудительно сохраняет текущий снимок каталога."""

        self._persist()

    def _ingest(self, offer: ProductOffer) -> CatalogUpsertResult:
        item = self._adapter.from_offer(offer)
        return self._catalog.upsert_with_result(item)

    def _persist(self) -> None:
        if self._storage is None:
            return
        self._storage.save(self._catalog.products)

    def _restore_fail_open(self) -> None:
        if self._storage is None:
            return

        try:
            products = self._storage.load()
            self._catalog.restore(products)
        except Exception:
            logger.exception(
                "Catalog snapshot restore failed: path=%s",
                self._storage.path,
            )

    def _record_report(self, report: CatalogIngestReport) -> None:
        product_count = len(report.product_keys)
        current = self._metrics
        self._metrics = CatalogMetrics(
            batches=current.batches + 1,
            total_offers=current.total_offers + report.total_offers,
            created_products=(
                current.created_products + report.created_products
            ),
            merged_offers=current.merged_offers + report.merged_offers,
            updated_offers=(
                current.updated_offers + report.updated_offers
            ),
            single_product_batches=(
                current.single_product_batches + int(product_count == 1)
            ),
            ambiguous_batches=(
                current.ambiguous_batches + int(product_count > 1)
            ),
            empty_batches=(
                current.empty_batches + int(report.total_offers == 0)
            ),
            lookup_hits=current.lookup_hits,
            lookup_misses=current.lookup_misses,
        )

    @classmethod
    def _storage_from_environment(cls) -> CatalogStorage | None:
        database_path = os.getenv(cls._database_path_env, "").strip()
        json_path = os.getenv(cls._storage_path_env, "").strip()

        if database_path:
            storage = SqliteCatalogStorage(database_path)
            if json_path:
                try:
                    imported = storage.import_json_if_empty(
                        JsonCatalogStorage(json_path)
                    )
                except Exception:
                    logger.exception(
                        "Catalog JSON to SQLite migration failed: "
                        "json=%s sqlite=%s",
                        json_path,
                        database_path,
                    )
                else:
                    if imported:
                        logger.info(
                            "Catalog JSON imported into SQLite: "
                            "products=%d json=%s sqlite=%s",
                            imported,
                            json_path,
                            database_path,
                        )
            return storage

        if json_path:
            return JsonCatalogStorage(json_path)
        return None

    @staticmethod
    def _build_report(
        results: tuple[CatalogUpsertResult, ...],
    ) -> CatalogIngestReport:
        actions = tuple(result.action for result in results)
        product_keys = tuple(
            dict.fromkeys(result.product.key for result in results)
        )
        return CatalogIngestReport(
            total_offers=len(results),
            created_products=actions.count(CatalogUpsertAction.CREATED),
            merged_offers=actions.count(CatalogUpsertAction.MERGED),
            updated_offers=actions.count(CatalogUpsertAction.UPDATED),
            product_keys=product_keys,
        )
