import asyncio
import logging
import re

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.sources.five_element import (
    FiveElementSource,
)
from app.sources.onliner import OnlinerSource
from app.sources.twenty_one_vek import (
    TwentyOneVekSource,
)


logger = logging.getLogger(__name__)


class PriceService:
    """Сервис поиска и сравнения цен."""

    def __init__(self) -> None:
        self._onliner_source = OnlinerSource()

        self._five_element_source = (
            FiveElementSource()
        )

        self._twenty_one_vek_source = (
            TwentyOneVekSource()
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
        """Ищет карточки через поиск 5 элемента."""

        return await self._five_element_source.find_products(
            query=query,
            limit=5,
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

    async def search_twenty_one_vek_url(
        self,
        url: str,
    ) -> list[ProductOffer]:
        """Получает товар из 21vek."""

        offers = (
            await self
            ._twenty_one_vek_source
            .search(url)
        )

        return self._prepare_offers(
            offers=offers,
            limit=1,
        )

    async def search_all_sources_by_onliner_key(
        self,
        product_key: str,
    ) -> list[ProductOffer]:
        """Собирает общий топ цен для выбранной модели."""

        onliner_offers = (
            await self.search_onliner_key(
                product_key
            )
        )

        if not onliner_offers:
            return []

        canonical_title = onliner_offers[0].title
        cross_source_query = (
            self._build_cross_source_query(
                canonical_title
            )
        )

        five_result, twenty_one_result = (
            await asyncio.gather(
                self._search_five_element_by_query(
                    query=cross_source_query,
                    canonical_title=canonical_title,
                ),
                self._twenty_one_vek_source.find_offers(
                    query=cross_source_query,
                    limit=20,
                ),
                return_exceptions=True,
            )
        )

        combined_offers = list(onliner_offers)

        for source_name, result in (
            ("5element", five_result),
            ("21vek", twenty_one_result),
        ):
            if isinstance(result, BaseException):
                logger.warning(
                    "%s aggregate search failed: %s",
                    source_name,
                    result,
                )
                continue

            combined_offers.extend(
                offer
                for offer in result
                if self._matches_model(
                    canonical_title,
                    offer.title,
                )
            )

        return self._prepare_aggregate_offers(
            offers=combined_offers,
            limit=5,
        )

    async def _search_five_element_by_query(
        self,
        query: str,
        canonical_title: str,
    ) -> list[ProductOffer]:
        """Получает цену лучшей карточки 5 элемента."""

        products = await self.find_five_element_products(
            query
        )

        for product in products:
            if self._matches_model(
                canonical_title,
                product.title,
            ):
                return (
                    await self
                    .search_five_element_key(
                        product.key
                    )
                )

        return []

    @staticmethod
    def _build_cross_source_query(
        title: str,
    ) -> str:
        """Убирает цвет и магазинный код из запроса."""

        query = re.sub(
            r"[()]",
            " ",
            title,
        )
        query = re.sub(
            r"\bSM-[A-Z0-9-]+\b",
            " ",
            query,
            flags=re.IGNORECASE,
        )
        query = query.replace("/", " ")

        return " ".join(query.split())
    
    async def search_five_element_key(
        self,
        product_key: str,
    ) -> list[ProductOffer]:
        """Получает выбранный товар 5 элемента."""

        return await self._five_element_source.search_by_key(
            product_key,
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

    @classmethod
    def _prepare_aggregate_offers(
        cls,
        offers: list[ProductOffer],
        limit: int,
    ) -> list[ProductOffer]:
        """Формирует топ с представителем каждого источника."""

        sorted_offers = cls._prepare_offers(
            offers=offers,
            limit=len(offers),
        )

        selected: list[ProductOffer] = []
        selected_ids: set[int] = set()
        represented_sources: set[str] = set()

        for offer in sorted_offers:
            if offer.source in represented_sources:
                continue

            selected.append(offer)
            selected_ids.add(id(offer))
            represented_sources.add(offer.source)

        for offer in sorted_offers:
            if len(selected) >= limit:
                break

            if id(offer) in selected_ids:
                continue

            selected.append(offer)
            selected_ids.add(id(offer))

        return sorted(
            selected[:limit],
            key=lambda offer: offer.price,
        )

    @staticmethod
    def _matches_model(
        canonical_title: str,
        candidate_title: str,
    ) -> bool:
        """Не смешивает базовую, Pro, Max и другие версии."""

        def normalize(value: str) -> str:
            normalized = value.casefold()
            normalized = normalized.replace("ё", "е")
            return re.sub(
                r"[^a-zа-я0-9]+",
                " ",
                normalized,
            ).strip()

        canonical = normalize(canonical_title)
        candidate = normalize(candidate_title)

        def model_codes(value: str) -> set[str]:
            """Находит цельные артикулы вроде HBA534EB3."""

            return {
                token
                for token in value.split()
                if (
                    len(token) >= 4
                    and re.search(r"[a-zа-я]", token)
                    and re.search(r"\d", token)
                )
            }

        canonical_model_codes = model_codes(canonical)
        candidate_model_codes = model_codes(candidate)

        if (
            canonical_model_codes
            and not canonical_model_codes.issubset(
                candidate_model_codes
            )
        ):
            return False

        memory_pattern = (
            r"\b(\d+)\s*"
            r"(gb|tb|mb|гб|тб|мб)\b"
        )

        unit_aliases = {
            "гб": "gb",
            "тб": "tb",
            "мб": "mb",
        }

        canonical_memory = {
            (
                amount,
                unit_aliases.get(unit, unit),
            )
            for amount, unit in re.findall(
                memory_pattern,
                canonical,
            )
        }
        candidate_memory = {
            (
                amount,
                unit_aliases.get(unit, unit),
            )
            for amount, unit in re.findall(
                memory_pattern,
                candidate,
            )
        }

        if (
            canonical_memory
            and not canonical_memory.issubset(
                candidate_memory
            )
        ):
            return False

        memory_amounts = {
            amount
            for amount, _ in canonical_memory
        }
        canonical_numbers = {
            number
            for number in re.findall(
                r"\d+",
                canonical,
            )
            if (
                number not in memory_amounts
                and len(number) <= 2
            )
        }
        candidate_numbers = set(
            re.findall(r"\d+", candidate)
        )

        if (
            not canonical_model_codes
            and not canonical_numbers.issubset(
                candidate_numbers
            )
        ):
            return False

        def version_tokens(value: str) -> set[str]:
            tokens = set(
                re.findall(
                    r"[a-zа-я]+|\d+",
                    value,
                )
            )
            markers = {
                "pro",
                "max",
                "plus",
                "ultra",
                "air",
                "mini",
                "lite",
                "fe",
                "e",
            }
            return tokens & markers

        return (
            version_tokens(canonical)
            == version_tokens(candidate)
        )
