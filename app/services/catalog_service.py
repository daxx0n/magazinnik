from collections.abc import Iterable

from app.models.catalog import MasterCatalogProduct
from app.models.offer import ProductOffer
from app.services.catalog_adapter import CatalogOfferAdapter
from app.services.master_catalog import MasterCatalog


class CatalogService:
    """Facade for feeding external offers into the master catalog.

    Keeps catalog logic isolated from source search services.
    """

    def __init__(
        self,
        catalog: MasterCatalog | None = None,
        adapter: CatalogOfferAdapter | None = None,
    ) -> None:
        self._catalog = catalog or MasterCatalog()
        self._adapter = adapter or CatalogOfferAdapter()

    @property
    def catalog(self) -> MasterCatalog:
        return self._catalog

    def ingest_offer(self, offer: ProductOffer) -> MasterCatalogProduct:
        item = self._adapter.from_offer(offer)
        return self._catalog.upsert(item)

    def ingest_offers(
        self,
        offers: Iterable[ProductOffer],
    ) -> tuple[MasterCatalogProduct, ...]:
        return tuple(
            self.ingest_offer(offer)
            for offer in offers
        )

    def search(self, query: str) -> list[MasterCatalogProduct]:
        return self._catalog.search(query)
