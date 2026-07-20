import logging
import os
from collections.abc import Iterable

from app.models.catalog import (
    CatalogIngestReport,
    CatalogUpsertAction,
    CatalogUpsertResult,
    MasterCatalogProduct,
)
from app.models.catalog_metrics import CatalogMetrics
from app.models.offer import ProductOffer
from app.services.catalog_adapter import CatalogOfferAdapter
from app.services.catalog_storage import JsonCatalogStorage
from app.services.master_catalog import MasterCatalog


logger = logging.getLogger(__name__)


class CatalogService:
    """Координирует адаптацию, дедупликацию и сохранение офферов."""

    _storage_path_env = "CATALOG_STORAGE_PATH"

    def __init__(
        self,
        catalog: MasterCatalog | None = None,
        adapter: CatalogOfferAdapter | None = None,
        storage: JsonCatalogStorage | None = None,
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
        self._metrics = CatalogMetrics(
            **{
                **self._metrics.__dict__,
                "lookup_hits": (
                    self._metrics.lookup_hits + (product is not None)
                ),
                "lookup_misses": (
                    self._metrics.lookup_misses + (product is None)
                ),
            }
        )
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
                current.single_product_batches + (product_count == 1)
            ),
            ambiguous_batches=(
                current.ambiguous_batches + (product_count > 1)
            ),
            empty_batches=(
                current.empty_batches + (report.total_offers == 0)
            ),
            lookup_hits=current.lookup_hits,
            lookup_misses=current.lookup_misses,
        )

    @classmethod
    def _storage_from_environment(cls) -> JsonCatalogStorage | None:
        raw_path = os.getenv(cls._storage_path_env, "").strip()
        if not raw_path:
            return None
        return JsonCatalogStorage(raw_path)

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
