import asyncio

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.five_element_index import (
    FiveElementIndex,
)
from app.sources.five_element import (
    FiveElementSource,
)
from app.sources.onliner import OnlinerSource


class PriceService:
    """Сервис поиска и сравнения цен."""

    def __init__(self) -> None:
        self._onliner_source = OnlinerSource()

        self._five_element_source = (
            FiveElementSource()
        )

        self._five_element_index = (
            FiveElementIndex()
        )

    async def find_onliner_products(
        self,
        query: str,
    ) -> list[ProductCandidate]:
        """Ищет карточки Onliner."""

        return (
            await self
            ._onliner_source
            .find_products(
                query=query,
                limit=5,
            )
        )

    async def find_five_element_products(
        self,
        query: str,
    ) -> list[ProductCandidate]:
        """Ищет карточки 5 элемента локально."""

        return await asyncio.to_thread(
            self._five_element_index.find_products,
            query,
            5,
        )

    async def search_onliner_url(
        self,
        url: str,
    ) -> list[ProductOffer]:
        """Получает предложения Onliner."""

        offers = (
            await self
            ._onliner_source
            .search(url)
        )

        return self._prepare_offers(
            offers=offers,
            limit=5,
        )

    async def search_onliner_key(
        self,
        product_key: str,
    ) -> list[ProductOffer]:
        """Получает выбранный товар Onliner."""

        offers = (
            await self
            ._onliner_source
            .search_by_key(
                product_key
            )
        )

        return self._prepare_offers(
            offers=offers,
            limit=5,
        )

    async def search_five_element_url(
        self,
        url: str,
    ) -> list[ProductOffer]:
        """Получает товар из 5 элемента."""

        offers = (
            await self
            ._five_element_source
            .search(url)
        )

        return self._prepare_offers(
            offers=offers,
            limit=1,
        )

    async def search_five_element_key(
        self,
        product_key: str,
    ) -> list[ProductOffer]:
        """Получает выбранный товар 5 элемента."""

        candidate = await asyncio.to_thread(
            self._five_element_index.get_by_key,
            product_key,
        )

        return await self.search_five_element_url(
            candidate.url
        )

    async def compare_urls(
        self,
        onliner_url: str,
        five_element_url: str,
    ) -> list[ProductOffer]:
        """Сравнивает Onliner и 5 элемент."""

        onliner_result, five_result = (
            await asyncio.gather(
                self.search_onliner_url(
                    onliner_url
                ),
                self.search_five_element_url(
                    five_element_url
                ),
            )
        )

        combined_offers = [
            *onliner_result,
            *five_result,
        ]

        return self._prepare_offers(
            offers=combined_offers,
            limit=6,
        )

    @staticmethod
    def _prepare_offers(
        offers: list[ProductOffer],
        limit: int,
    ) -> list[ProductOffer]:
        """Фильтрует и сортирует предложения."""

        available_offers = [
            offer
            for offer in offers
            if offer.available
        ]

        sorted_offers = sorted(
            available_offers,
            key=lambda offer: offer.price,
        )

        return sorted_offers[:limit]