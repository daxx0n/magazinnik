from collections.abc import Iterable

from app.models.catalog import (
    CatalogIngestReport,
    CatalogUpsertAction,
    CatalogUpsertResult,
    MasterCatalogProduct,
)
from app.models.offer import ProductOffer
from app.services.catalog_adapter import CatalogOfferAdapter
from app.services.catalog_storage import JsonCatalogStorage
from app.services.master_catalog import MasterCatalog


class CatalogService:
    """Координирует адаптацию, дедупликацию и сохранение офферов."""

    def __init__(
        self,
        catalog: MasterCatalog | None = None,
        adapter: CatalogOfferAdapter | None = None,
        storage: JsonCatalogStorage | None = None,
        restore_on_start: bool = True,
    ) -> None:
        self._catalog = catalog or MasterCatalog()
        self._adapter = adapter or CatalogOfferAdapter()
        self._storage = storage
        self._last_report = CatalogIngestReport(
            total_offers=0,
            created_products=0,
            merged_offers=0,
            updated_offers=0,
        )

        if self._storage is not None and restore_on_start:
            self._catalog.restore(self._storage.load())

    @property
    def catalog(self) -> MasterCatalog:
        return self._catalog

    @property
    def last_report(self) -> CatalogIngestReport:
        return self._last_report

    def ingest_offer(self, offer: ProductOffer) -> MasterCatalogProduct:
        result = self._ingest(offer)
        self._last_report = self._build_report((result,))
        self._persist()
        return result.product

    def ingest_offers(
        self,
        offers: Iterable[ProductOffer],
    ) -> tuple[MasterCatalogProduct, ...]:
        results = tuple(self._ingest(offer) for offer in offers)
        self._last_report = self._build_report(results)
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
