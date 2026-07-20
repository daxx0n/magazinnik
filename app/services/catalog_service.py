import asyncio
import asyncio
import asyncio
import logging
import os
import threading
from functools import wraps
import threading
from functools import wraps
import threading
from functools import wraps
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.models.catalog import (
    CatalogIngestReport,
    CatalogSnapshotMetrics,
    CatalogUpsertAction,
    CatalogUpsertResult,
    ExternalCatalogItem,
    MasterCatalogProduct,
    MatchReview,
)
from app.models.catalog_metrics import CatalogMetrics
from app.models.offer import ProductOffer
from app.services.catalog_adapter import CatalogOfferAdapter
from app.services.catalog_search import search_catalog
from app.services.catalog_storage import JsonCatalogStorage
from app.services.master_catalog import MasterCatalog
from app.services.sqlite_catalog_storage import SqliteCatalogStorage


logger = logging.getLogger(__name__)


CatalogStorage = JsonCatalogStorage | SqliteCatalogStorage


def synchronized(method):
    """Сериализует доступ к общему in-memory каталогу из event loop и threads."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def synchronized(method):
    """Сериализует доступ к общему in-memory каталогу из event loop и threads."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def synchronized(method):
    """Сериализует доступ к общему in-memory каталогу из event loop и threads."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


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
        self._lock = threading.RLock()

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

    @synchronized
    def ingest_offer(self, offer: ProductOffer) -> MasterCatalogProduct:
        result = self._ingest(offer)
        self._last_report = self._build_report((result,))
        self._record_report(self._last_report)
        self._persist()
        return result.product

    @synchronized
    def ingest_offers(
        self,
        offers: Iterable[ProductOffer],
    ) -> tuple[MasterCatalogProduct, ...]:
        results = tuple(self._ingest(offer) for offer in offers)
        self._last_report = self._build_report(results)
        self._record_report(self._last_report)
        self._persist()
        return tuple(result.product for result in results)

    @synchronized
    def ingest_offers_with_report(
        self,
        offers: Iterable[ProductOffer],
    ) -> CatalogIngestReport:
        self.ingest_offers(offers)
        return self._last_report

    async def ingest_offers_with_report_async(
        self,
        offers: Iterable[ProductOffer],
    ) -> CatalogIngestReport:
        """Сохраняет каталог вне event loop, сериализуя конкурентные записи."""

        offer_tuple = tuple(offers)
        return await asyncio.to_thread(
            self.ingest_offers_with_report,
            offer_tuple,
        )

    async def ingest_offers_with_report_async(
        self,
        offers: Iterable[ProductOffer],
    ) -> CatalogIngestReport:
        """Сохраняет каталог вне event loop, сериализуя конкурентные записи."""

        offer_tuple = tuple(offers)
        return await asyncio.to_thread(
            self.ingest_offers_with_report,
            offer_tuple,
        )

    @synchronized
    async def ingest_offers_with_report_async(
        self,
        offers: Iterable[ProductOffer],
    ) -> CatalogIngestReport:
        """Сохраняет каталог вне event loop, сериализуя конкурентные записи."""

        offer_tuple = tuple(offers)
        return await asyncio.to_thread(
            self.ingest_offers_with_report,
            offer_tuple,
        )

    @synchronized
    def ingest_external_items_with_report(
        self,
        items: Iterable[ExternalCatalogItem],
        *,
        deactivate_missing_source: str | None = None,
    ) -> CatalogIngestReport:
        """Транзакционно импортирует внешний batch или полный snapshot."""

        item_tuple = tuple(items)
        snapshot_source = (
            deactivate_missing_source.strip()
            if deactivate_missing_source is not None
            else None
        )
        if snapshot_source == "":
            raise ValueError("Snapshot source must not be empty")
        if snapshot_source is not None and not item_tuple:
            raise ValueError("Snapshot feed must contain at least one item")

        normalized_snapshot_source = (
            snapshot_source.casefold()
            if snapshot_source is not None
            else None
        )
        if normalized_snapshot_source is not None and any(
            item.source.strip().casefold() != normalized_snapshot_source
            for item in item_tuple
        ):
            raise ValueError(
                "Snapshot feed must contain exactly one source"
            )

        snapshot = deepcopy(self._catalog.products)
        try:
            results = tuple(
                self._catalog.upsert_with_result(item)
                for item in item_tuple
            )
            report = self._build_report(results)
            if snapshot_source is not None:
                seen_external_ids = {
                    item.external_id.strip()
                    for item in item_tuple
                }
                deactivated = self._deactivate_missing_offers(
                    source=snapshot_source,
                    seen_external_ids=seen_external_ids,
                    updated_at=datetime.now(timezone.utc),
                )
                report = replace(
                    report,
                    deactivated_offers=deactivated,
                )
            self._persist()
        except Exception:
            self._catalog.restore(snapshot)
            raise

        self._last_report = report
        self._record_report(report)
        return report

    @synchronized
    def search(self, query: str) -> list[MasterCatalogProduct]:
        """Ищет по названиям, нормализованной модели, MPN и EAN."""

        return search_catalog(self._catalog.products, query)

    @synchronized
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

    @synchronized
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

    @synchronized
    def pending_reviews(self, limit: int = 20) -> tuple[MatchReview, ...]:
        """Возвращает спорные пары, сохранённые вместе с офферами."""

        return self._catalog.pending_reviews(limit=limit)

    @synchronized
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

    @synchronized
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

    @synchronized
    def save(self) -> None:
        """Принудительно сохраняет текущий снимок каталога."""

        self._persist()

    def _ingest(self, offer: ProductOffer) -> CatalogUpsertResult:
        item = self._adapter.from_offer(offer)
        return self._catalog.upsert_with_result(item)

    def _deactivate_missing_offers(
        self,
        *,
        source: str,
        seen_external_ids: set[str],
        updated_at: datetime,
    ) -> int:
        normalized_source = source.strip().casefold()
        deactivated = 0
        for product in self._catalog.products:
            for index, offer in enumerate(product.offers):
                if (
                    offer.source.strip().casefold() != normalized_source
                    or offer.external_id.strip() in seen_external_ids
                    or not offer.available
                ):
                    continue
                product.offers[index] = replace(
                    offer,
                    available=False,
                    updated_at=updated_at,
                )
                deactivated += 1
        return deactivated

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
