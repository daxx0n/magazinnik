import asyncio
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from functools import partial
from typing import Any, TypeVar

from app.models.category import ProductCategory
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import (
    ComparisonResult,
    MatchDecision,
    SourceSearchStatus,
)
from app.sources import ProductNotFoundError
from app.sources.five_element import (
    FiveElementSource,
)
from app.sources.onliner import OnlinerSource
from app.sources.shop_by import ShopBySource
from app.sources.twenty_one_vek import (
    TwentyOneVekSource,
)
from app.services.product_variants import (
    display_color,
    extract_color,
    extract_color_key,
    extract_memory,
)


logger = logging.getLogger(__name__)


SearchItem = TypeVar("SearchItem")


class PriceService:
    """Сервис поиска и сравнения цен."""

    _aggregate_search_limit = 100
    _source_search_cache_ttl = 30.0
    _source_search_cache_size = 256
    _candidate_cache_size = 20_000

    def __init__(self) -> None:
        self._onliner_candidates: OrderedDict[
            str,
            ProductCandidate,
        ] = OrderedDict()
        self._onliner_queries: OrderedDict[
            str,
            str,
        ] = OrderedDict()

        self._onliner_source = OnlinerSource()

        self._five_element_source = (
            FiveElementSource()
        )

        self._twenty_one_vek_source = (
            TwentyOneVekSource()
        )

        self._shop_by_source = ShopBySource()

        self._source_search_cache: OrderedDict[
            tuple[str, str, int],
            tuple[float, list[Any]],
        ] = OrderedDict()
        self._source_search_tasks: dict[
            tuple[str, str, int],
            asyncio.Task[list[Any]],
        ] = {}

    async def find_onliner_products(
        self,
        query: str,
        category: str | None = None,
    ) -> list[ProductCandidate]:
        """Ищет карточки Onliner."""

        products = (
            await self
            ._onliner_source
            .find_products(
                query=query,
                limit=None,
                category=category,
            )
        )

        for product in products:
            self._onliner_candidates[product.key] = product
            self._onliner_candidates.move_to_end(product.key)
            self._onliner_queries[product.key] = query
            self._onliner_queries.move_to_end(product.key)

        while len(self._onliner_candidates) > self._candidate_cache_size:
            expired_key, _ = self._onliner_candidates.popitem(
                last=False
            )
            self._onliner_queries.pop(expired_key, None)

        return products

    async def find_onliner_categories(
        self,
        query: str,
    ) -> list[ProductCategory]:
        """Находит разделы каталога для широкого запроса."""

        return await self._onliner_source.find_categories(query)

    @staticmethod
    def should_categorize_query(query: str) -> bool:
        """Определяет короткий запрос без конкретной модели."""

        tokens = re.findall(
            r"[a-zа-яё0-9]+",
            query.casefold(),
        )

        return (
            1 <= len(tokens) <= 2
            and not any(
                character.isdigit()
                for character in query
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
    ) -> ComparisonResult:
        """Собирает общий топ цен для выбранной модели."""

        search_started = time.monotonic()
        selected_candidate = (
            self._onliner_candidates.get(product_key)
        )

        if selected_candidate is not None:
            canonical_title = selected_candidate.title
        else:
            (
                onliner_result,
                onliner_duration,
            ) = await self._timed_result(
                self.search_onliner_key(product_key)
            )

            if isinstance(onliner_result, BaseException):
                raise onliner_result

            onliner_offers = onliner_result

            if not onliner_offers:
                raise ProductNotFoundError(
                    "Не удалось определить выбранную модель."
                )

            canonical_title = onliner_offers[0].title

        requested_query = self._onliner_queries.get(
            product_key,
            canonical_title,
        )
        cross_source_query = (
            self._build_cross_source_query(
                canonical_title
            )
        )

        logger.info(
            "Aggregate search: model=%r query=%r",
            canonical_title,
            cross_source_query,
        )

        external_searches = (
            self._timed_result(
                self._search_five_element_by_query(
                    query=cross_source_query,
                    canonical_title=canonical_title,
                    requested_title=requested_query,
                )
            ),
            self._timed_result(
                self._search_twenty_one_vek_by_query(
                    query=cross_source_query,
                    canonical_title=canonical_title,
                )
            ),
            self._timed_result(
                self._search_shop_by_query(
                    query=cross_source_query,
                    canonical_title=canonical_title,
                )
            ),
        )

        if selected_candidate is not None:
            (
                (onliner_result, onliner_duration),
                (five_result, five_duration),
                (twenty_one_result, twenty_one_duration),
                (shop_by_result, shop_by_duration),
            ) = await asyncio.gather(
                self._timed_result(
                    self.search_onliner_key(product_key)
                ),
                *external_searches,
            )

            if isinstance(onliner_result, BaseException):
                onliner_offers = []
                onliner_state = (
                    "not_found"
                    if isinstance(
                        onliner_result,
                        ProductNotFoundError,
                    )
                    else "unavailable"
                )
                log_method = (
                    logger.info
                    if isinstance(
                        onliner_result,
                        ProductNotFoundError,
                    )
                    else logger.warning
                )
                log_method(
                    "Onliner aggregate search failed: %s",
                    onliner_result,
                )
            else:
                onliner_offers = onliner_result
                onliner_state = (
                    "found" if onliner_offers else "not_found"
                )
        else:
            onliner_state = "found"
            (
                (five_result, five_duration),
                (twenty_one_result, twenty_one_duration),
                (shop_by_result, shop_by_duration),
            ) = await asyncio.gather(
                *external_searches,
            )

        combined_offers = list(onliner_offers)
        match_decisions: list[MatchDecision] = []
        source_statuses = [
            SourceSearchStatus(
                source="Onliner",
                state=onliner_state,
                matched_offers=len(onliner_offers),
                checked_candidates=len(onliner_offers),
                duration_seconds=onliner_duration,
            )
        ]

        for source_name, result, duration in (
            ("5 элемент", five_result, five_duration),
            ("21vek", twenty_one_result, twenty_one_duration),
            ("Shop.by", shop_by_result, shop_by_duration),
        ):
            if isinstance(result, BaseException):
                logger.warning(
                    "%s aggregate search failed: %s",
                    source_name,
                    result,
                )
                source_statuses.append(
                    SourceSearchStatus(
                        source=source_name,
                        state="unavailable",
                        duration_seconds=duration,
                    )
                )
                continue

            if source_name == "5 элемент":
                (
                    source_offers,
                    had_candidates,
                    source_decisions,
                ) = result
                match_decisions.extend(
                    source_decisions
                )
                checked_candidates = len(source_decisions)
            else:
                had_candidates = bool(result)
                checked_candidates = len(result)
                source_offers = []

                for offer in result:
                    mismatch_reason = (
                        self._model_mismatch_reason(
                            canonical_title,
                            offer.title,
                            requested_title=(
                                requested_query
                            ),
                        )
                    )
                    logger.info(
                        "Match decision: source=%s "
                        "candidate=%r accepted=%s reason=%s",
                        source_name,
                        offer.title,
                        mismatch_reason is None,
                        mismatch_reason or "exact_match",
                    )
                    match_decisions.append(
                        MatchDecision(
                            source=source_name,
                            title=offer.title,
                            accepted=(
                                mismatch_reason is None
                            ),
                            reason=(
                                mismatch_reason
                                or "exact_match"
                            ),
                        )
                    )

                    if mismatch_reason is None:
                        source_offers.append(offer)

            combined_offers.extend(source_offers)

            if source_offers:
                state = "found"
            elif had_candidates:
                state = "filtered"
            else:
                state = "not_found"

            source_statuses.append(
                SourceSearchStatus(
                    source=source_name,
                    state=state,
                    matched_offers=len(source_offers),
                    checked_candidates=checked_candidates,
                    duration_seconds=duration,
                )
            )

        offers = self._prepare_aggregate_offers(
            offers=combined_offers,
        )

        return ComparisonResult(
            offers=offers,
            source_statuses=source_statuses,
            match_decisions=match_decisions,
            query=requested_query,
            product_title=canonical_title,
            duration_seconds=(
                time.monotonic() - search_started
            ),
            completed_at=datetime.now().strftime(
                "%d.%m.%Y %H:%M:%S"
            ),
        )

    @staticmethod
    async def _timed_result(
        awaitable: Awaitable[SearchItem],
    ) -> tuple[SearchItem | BaseException, float]:
        """Измеряет операцию, сохраняя её обычную ошибку."""

        started = time.monotonic()

        try:
            result = await awaitable
        except Exception as error:
            result = error

        return result, time.monotonic() - started

    async def _search_five_element_by_query(
        self,
        query: str,
        canonical_title: str,
        requested_title: str,
    ) -> tuple[
        list[ProductOffer],
        bool,
        list[MatchDecision],
    ]:
        """Получает цену лучшей карточки 5 элемента."""

        search_queries = self._build_source_queries(
            query=query,
            canonical_title=canonical_title,
        )
        search_results = await asyncio.gather(
            *(
                self._cached_source_search(
                    source_name="5_element_products",
                    query=source_query,
                    limit=self._aggregate_search_limit,
                    loader=partial(
                        self._five_element_source.find_products,
                        query=source_query,
                        limit=self._aggregate_search_limit,
                    ),
                )
                for source_query in search_queries
            ),
            return_exceptions=True,
        )
        successful_results = [
            result
            for result in search_results
            if not isinstance(result, BaseException)
        ]

        if not successful_results:
            raise search_results[0]

        products = self._unique_candidates(
            product
            for result in successful_results
            for product in result
        )
        decisions: list[MatchDecision] = []

        for product in products:
            mismatch_reason = (
                self._model_mismatch_reason(
                    canonical_title,
                    product.title,
                    requested_title=requested_title,
                )
            )
            logger.info(
                "Match decision: source=5 элемент "
                "candidate=%r accepted=%s reason=%s",
                product.title,
                mismatch_reason is None,
                mismatch_reason or "exact_match",
            )
            decisions.append(
                MatchDecision(
                    source="5 элемент",
                    title=product.title,
                    accepted=mismatch_reason is None,
                    reason=(
                        mismatch_reason
                        or "exact_match"
                    ),
                )
            )

            if mismatch_reason is None:
                return (
                    (
                        await self
                        .search_five_element_key(
                            product.key
                        )
                    ),
                    True,
                    decisions,
                )

        return [], bool(products), decisions

    async def _search_twenty_one_vek_by_query(
        self,
        query: str,
        canonical_title: str,
    ) -> list[ProductOffer]:
        """Ищет 21vek по модели и вариантам цвета."""

        return await self._search_offer_source_by_query(
            source=self._twenty_one_vek_source,
            query=query,
            canonical_title=canonical_title,
        )

    async def _search_shop_by_query(
        self,
        query: str,
        canonical_title: str,
    ) -> list[ProductOffer]:
        """Ищет Shop.by по модели и вариантам цвета."""

        return await self._search_offer_source_by_query(
            source=self._shop_by_source,
            query=query,
            canonical_title=canonical_title,
        )

    async def _search_offer_source_by_query(
        self,
        source,
        query: str,
        canonical_title: str,
    ) -> list[ProductOffer]:
        """Объединяет выдачу источника по вариантам цвета."""

        search_results = await asyncio.gather(
            *(
                self._cached_source_search(
                    source_name=f"{source.source_name}_offers",
                    query=source_query,
                    limit=self._aggregate_search_limit,
                    loader=partial(
                        source.find_offers,
                        query=source_query,
                        limit=self._aggregate_search_limit,
                    ),
                )
                for source_query in self._build_source_queries(
                    query=query,
                    canonical_title=canonical_title,
                )
            ),
            return_exceptions=True,
        )
        successful_results = [
            result
            for result in search_results
            if not isinstance(result, BaseException)
        ]

        if not successful_results:
            raise search_results[0]

        unique: dict[
            tuple[str, str],
            ProductOffer,
        ] = {}

        for result in successful_results:
            for offer in result:
                unique.setdefault(
                    (
                        (offer.seller or "").casefold(),
                        offer.url,
                    ),
                    offer,
                )

        return list(unique.values())

    async def _cached_source_search(
        self,
        source_name: str,
        query: str,
        limit: int,
        loader: Callable[[], Awaitable[list[SearchItem]]],
    ) -> list[SearchItem]:
        """Повторно использует недавний одинаковый поиск."""

        normalized_query = " ".join(
            query.casefold().split()
        )
        cache_key = (
            source_name,
            normalized_query,
            limit,
        )
        cached = self._source_search_cache.get(cache_key)
        now = time.monotonic()

        if cached is not None:
            cached_at, cached_items = cached

            if now - cached_at <= self._source_search_cache_ttl:
                self._source_search_cache.move_to_end(cache_key)
                return list(cached_items)

            self._source_search_cache.pop(cache_key, None)

        task = self._source_search_tasks.get(cache_key)

        if task is None:
            task = asyncio.create_task(loader())
            self._source_search_tasks[cache_key] = task
            task.add_done_callback(
                partial(
                    self._complete_source_search,
                    cache_key,
                )
            )

        result = await asyncio.shield(task)
        return list(result)

    def _complete_source_search(
        self,
        cache_key: tuple[str, str, int],
        task: asyncio.Task[list[Any]],
    ) -> None:
        """Сохраняет успешный результат и освобождает задачу."""

        if self._source_search_tasks.get(cache_key) is task:
            self._source_search_tasks.pop(cache_key, None)

        if task.cancelled() or task.exception() is not None:
            return

        self._source_search_cache[cache_key] = (
            time.monotonic(),
            list(task.result()),
        )
        self._source_search_cache.move_to_end(cache_key)

        while (
            len(self._source_search_cache)
            > self._source_search_cache_size
        ):
            self._source_search_cache.popitem(last=False)

    @staticmethod
    def _build_source_queries(
        query: str,
        canonical_title: str,
    ) -> list[str]:
        """Добавляет варианты запроса с выбранным цветом."""

        color = extract_color(canonical_title)
        marketing_color = display_color(canonical_title)
        queries = []

        for suffix in (color, marketing_color, None):
            source_query = " ".join(
                part
                for part in (query, suffix)
                if part
            )

            if source_query.casefold() not in {
                item.casefold() for item in queries
            }:
                queries.append(source_query)

        return queries

    @staticmethod
    def _unique_candidates(
        products: Iterable[ProductCandidate],
    ) -> list[ProductCandidate]:
        """Убирает повторы карточек из нескольких запросов."""

        unique: dict[str, ProductCandidate] = {}

        for product in products:
            unique.setdefault(product.key, product)

        return list(unique.values())

    @staticmethod
    def _build_cross_source_query(
        title: str,
    ) -> str:
        """Убирает цвет и магазинный код из запроса."""

        query = re.sub(
            r"\([^()]*\)",
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
    ) -> list[ProductOffer]:
        """Оставляет минимальную цену каждого источника."""

        sorted_offers = cls._prepare_offers(
            offers=offers,
            limit=len(offers),
        )

        selected: list[ProductOffer] = []
        represented_sources: set[str] = set()

        for offer in sorted_offers:
            if offer.source in represented_sources:
                continue

            selected.append(offer)
            represented_sources.add(offer.source)

        return selected

    @classmethod
    def _matches_model(
        cls,
        canonical_title: str,
        candidate_title: str,
    ) -> bool:
        """Не смешивает базовую, Pro, Max и другие версии."""

        return cls._model_mismatch_reason(
            canonical_title,
            candidate_title,
        ) is None

    @staticmethod
    def _model_mismatch_reason(
        canonical_title: str,
        candidate_title: str,
        requested_title: str | None = None,
    ) -> str | None:
        """Возвращает причину несовпадения моделей."""

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

        canonical_tokens = canonical.split()
        candidate_tokens = set(candidate.split())

        generic_title_words = {
            "headphones",
            "laptop",
            "phone",
            "smartphone",
            "tv",
            "беспроводные",
            "духовой",
            "игровая",
            "кофемашина",
            "наушники",
            "ноутбук",
            "пылесос",
            "приставка",
            "робот",
            "смартфон",
            "телевизор",
            "телефон",
            "холодильник",
            "шкаф",
            "электрический",
        }

        canonical_brand = next(
            (
                token
                for token in canonical_tokens
                if (
                    token.isalpha()
                    and token
                    not in generic_title_words
                )
            ),
            None,
        )

        if (
            canonical_brand
            and canonical_brand
            not in candidate_tokens
        ):
            return "brand"

        accessory_markers = {
            "adapter",
            "case",
            "cable",
            "charger",
            "cover",
            "mount",
            "protector",
            "strap",
            "адаптер",
            "держател",
            "зарядн",
            "кабел",
            "креплен",
            "накладк",
            "пленк",
            "ремеш",
            "стекл",
            "чехол",
        }

        def is_accessory(value: str) -> bool:
            return any(
                token.startswith(marker)
                for token in value.split()
                for marker in accessory_markers
            )

        if (
            is_accessory(candidate)
            and not is_accessory(canonical)
        ):
            return "accessory"

        canonical_color = extract_color_key(
            canonical_title
        )
        candidate_color = extract_color_key(
            candidate_title
        )

        if (
            canonical_color is not None
            and candidate_color is not None
            and canonical_color != candidate_color
        ):
            return "color"

        def model_codes(
            original_value: str,
            normalized_value: str,
        ) -> set[str]:
            """Извлекает произвольные буквенно-цифровые коды."""

            codes = {
                token
                for token in normalized_value.split()
                if (
                    len(token) >= 4
                    and re.search(r"[a-zа-я]", token)
                    and re.search(r"\d", token)
                    and not re.fullmatch(
                        r"\d+(?:gb|tb|mb|гб|тб|мб)",
                        token,
                    )
                )
            }

            # Некоторые магазины разделяют части одного артикула
            # дефисами или слешами: HBA-534-EB3 и HBA534EB3
            # должны считаться одним кодом.
            for raw_code in re.findall(
                r"[a-zа-я0-9]+"
                r"(?:[-_/.][a-zа-я0-9]+)+",
                original_value.casefold(),
            ):
                if re.fullmatch(
                    r"\d+(?:gb|tb|mb|гб|тб|мб)?"
                    r"(?:[/_-]\d+"
                    r"(?:gb|tb|mb|гб|тб|мб)?)+",
                    raw_code,
                ):
                    continue

                compact_code = re.sub(
                    r"[^a-zа-я0-9]",
                    "",
                    raw_code,
                )

                if (
                    len(compact_code) >= 4
                    and (
                        (
                            re.search(
                                r"[a-zа-я]",
                                compact_code,
                            )
                            and re.search(
                                r"\d",
                                compact_code,
                            )
                        )
                        or (
                            compact_code.isdigit()
                            and len(compact_code) >= 6
                        )
                    )
                ):
                    codes.add(compact_code)

            return codes

        code_reference_title = (
            requested_title
            if requested_title is not None
            else canonical_title
        )
        normalized_code_reference = normalize(
            code_reference_title
        )
        reference_model_codes = model_codes(
            code_reference_title,
            normalized_code_reference,
        )
        candidate_model_codes = model_codes(
            candidate_title,
            candidate,
        )

        def short_model_codes(value: str) -> set[str]:
            return {
                token
                for token in value.split()
                if (
                    2 <= len(token) <= 3
                    and re.search(r"[a-zа-я]", token)
                    and re.search(r"\d", token)
                    and not re.fullmatch(
                        r"\d+(?:gb|tb|mb|гб|тб|мб)",
                        token,
                    )
                )
            }

        def compatible_codes(
            first: str,
            second: str,
        ) -> bool:
            if first == second:
                return True

            shorter, longer = sorted(
                (first, second),
                key=len,
            )
            return (
                len(shorter) >= 5
                and longer.endswith(shorter)
            )

        has_compatible_code = False

        if reference_model_codes:
            has_compatible_code = any(
                compatible_codes(reference, candidate_code)
                for reference in reference_model_codes
                for candidate_code in candidate_model_codes
            )

            if not has_compatible_code:
                return "model_code"

        reference_short_codes = short_model_codes(
            normalized_code_reference
        )
        candidate_short_codes = short_model_codes(
            candidate
        )

        if (
            not has_compatible_code
            and not reference_short_codes.issubset(
                candidate_short_codes
            )
        ):
            return "model_number"

        def memory_specs(value: str) -> set[tuple[str, str]]:
            label = extract_memory(value)

            if label is None:
                return set()

            return {
                (amount, unit.casefold())
                for amount, unit in re.findall(
                    r"(\d+)(MB|GB|TB)",
                    label,
                    flags=re.IGNORECASE,
                )
            }

        canonical_memory = memory_specs(canonical_title)
        candidate_memory = memory_specs(candidate_title)

        if (
            canonical_memory
            and not canonical_memory.issubset(
                candidate_memory
            )
        ):
            return "memory"

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
            not reference_model_codes
            and not canonical_numbers.issubset(
                candidate_numbers
            )
        ):
            return "model_number"

        def sim_configuration(value: str) -> str:
            compact = re.sub(
                r"[^a-zа-я0-9+]+",
                " ",
                value.casefold().replace("ё", "е"),
            )

            if re.search(r"\bdual\s+e\s*sim\b", compact):
                return "dual_esim"

            if re.search(r"\bdual\s+sim\b", compact):
                return "dual_sim"

            if re.search(
                r"\b(?:только\s+)?e\s*sim\b",
                compact,
            ) and not re.search(
                r"\b(?:nano\s+)?sim\s*\+\s*e\s*sim\b",
                compact,
            ):
                return "esim_only"

            return "standard"

        if sim_configuration(
            canonical_title
        ) != sim_configuration(candidate_title):
            return "sim"

        def version_tokens(value: str) -> set[str]:
            value = re.sub(
                r"\be\s+sim\b",
                " ",
                value,
            )
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

        if (
            version_tokens(canonical)
            != version_tokens(candidate)
        ):
            return "version"

        return None
