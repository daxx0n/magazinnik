import hashlib

from app.models.catalog import ExternalCatalogItem
from app.models.offer import ProductOffer
from app.services.product_identity import ProductIdentityBuilder


class CatalogOfferAdapter:
    """Преобразует текущие предложения магазинов в записи мастер-каталога."""

    def __init__(self) -> None:
        self._identity_builder = ProductIdentityBuilder()

    def from_offer(self, offer: ProductOffer) -> ExternalCatalogItem:
        """Создаёт стабильную внешнюю карточку из ProductOffer."""

        return ExternalCatalogItem(
            source=offer.source,
            external_id=self._external_id(offer),
            title=offer.title,
            url=offer.url,
            price=offer.price,
            currency=offer.currency,
            available=offer.available,
            identity=self._identity_builder.build(offer.title),
        )

    @staticmethod
    def _external_id(offer: ProductOffer) -> str:
        """Использует URL как устойчивый идентификатор предложения."""

        normalized_url = offer.url.strip().casefold()
        if normalized_url:
            return hashlib.sha256(
                normalized_url.encode("utf-8")
            ).hexdigest()[:24]

        fallback = "|".join(
            (
                offer.source.strip().casefold(),
                offer.title.strip().casefold(),
                offer.seller.strip().casefold() if offer.seller else "",
            )
        )
        return hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]
