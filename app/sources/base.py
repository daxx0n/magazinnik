from typing import Protocol

from app.models.offer import ProductOffer


class PriceSource(Protocol):
    """Общий интерфейс источника цен."""

    source_name: str

    async def search(self, query: str) -> list[ProductOffer]:
        """Ищет предложения по запросу."""
        ...