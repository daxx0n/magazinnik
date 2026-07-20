from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.models.catalog import MasterCatalogProduct
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import ComparisonResult, SourceSearchStatus
from app.services.catalog_service import CatalogService
from app.services.model_selection import (
    collapse_color_variants,
    generation_mismatch,
    requested_color_key,
)
from app.services.price_service import PriceService
from app.sources import ProductNotFoundError


logger = logging.getLogger(__name__)


class CatalogFirstPriceService(PriceService):
    """Ищет в мастер-каталоге и использует live-search как fallback."""

    _catalog_key_prefix = "catalog:"
    _catalog_query_cache_size = 2_000
    _default_freshness_hours = 24.0

    def __init__(
        self,
        catalog_service: CatalogService | None = None,
        catalog_presentation_enabled: bool | None = None,
        catalog_search_enabled: bool | None = None,
        freshness_hours: float | None = None,
    ) -> None:
        super().__init__(
            catalog_service=catalog_service,
            catalog_presentation_enabled=catalog_presentation_enabled,
        )
        self._catalog_search_enabled = (
            catalog_search_enabled
            if catalog_search_enabled is not None
            else self._env_flag("MASTER_CATALOG_SEARCH_ENABLED")
        )
        self._catalog_freshness = timedelta(
            hours=(
                freshness_hours
                if freshness_hours is not None
                else self._freshness_hours_from_environment()
            )
        )
        self._catalog_queries: OrderedDict[str, str] = OrderedDict()

    async def find_onliner_products(
        self,
        query: str,
        category: str | None = None,
    ) -> list[ProductCandidate]:
        """Возвращает мастер-карточки, сохраняя Onliner fallback."""

        if not self._catalog_search_enabled or category is not None:
            products = await super().find_onliner_products(query, category)
            return collapse_color_variants(products, query)

        try:
            products = self._catalog_service.search(query)
        except Exception:
            logger.exception("Master catalog search failed; using Onliner fallback")
        else:
            candidates = [
                candidate
                for product in products
                if (candidate := self._candidate_from_product(product)) is not None
            ]
            if candidates:
                for candidate in candidates:
                    self._remember_catalog_query(candidate.key, query)
                logger.info(
                    "Master catalog search hit: query=%r products=%d",
                    query,
                    len(candidates),
                )
                return candidates

        products = await super().find_onliner_products(query, category)
        return collapse_color_variants(products, query)

    async def search_all_sources_by_onliner_key(
        self,
        product_key: str,
    ) -> ComparisonResult:
        """Открывает мастер-карточку или обновляет её через live-search."""

        if (
            not self._catalog_search_enabled
            or not product_key.startswith(self._catalog_key_prefix)
        ):
            return await super().search_all_sources_by_onliner_key(product_key)

        started = time.monotonic()
        master_key = product_key.removeprefix(self._catalog_key_prefix)
        product = self._catalog_service.get_product(master_key)
        if product is None:
            raise ProductNotFoundError("Мастер-карточка больше не существует.")

        query = self._catalog_queries.get(product_key, product.title)
        fresh_offers = self._catalog_offers(product, fresh_only=True)
        if fresh_offers:
            logger.info(
                "Master catalog fresh hit: product=%s offers=%d",
                product.key,
                len(fresh_offers),
            )
            return self._catalog_comparison(
                product=product,
                product_key=product_key,
                query=query,
                offers=fresh_offers,
                started=started,
            )

        try:
            candidates = await super().find_onliner_products(product.title)
            live_candidate = self._select_live_candidate(
                product.title,
                candidates,
                requested_title=query,
            )
            if live_candidate is not None:
                self._onliner_queries[live_candidate.key] = query
                logger.info(
                    "Master catalog stale; refreshing live: product=%s onliner=%s",
                    product.key,
                    live_candidate.key,
                )
                result = await super().search_all_sources_by_onliner_key(
                    live_candidate.key
                )
                return replace(
                    result,
                    product_key=product_key,
                    query=query,
                    master_product_key=(
                        result.master_product_key or product.key
                    ),
                    master_product_title=(
                        result.master_product_title or product.title
                    ),
                    catalog_presentation=True,
                )
        except Exception:
            logger.exception(
                "Master catalog live refresh failed; using stored offers: %s",
                product.key,
            )

        stored_offers = self._catalog_offers(product, fresh_only=False)
        if stored_offers:
            return self._catalog_comparison(
                product=product,
                product_key=product_key,
                query=query,
                offers=stored_offers,
                started=started,
            )

        raise ProductNotFoundError(
            "В мастер-каталоге нет доступных предложений, "
            "а live-поиск не нашёл товар."
        )

    @staticmethod
    def _model_mismatch_reason(
        canonical_title: str,
        candidate_title: str,
        requested_title: str | None = None,
    ) -> str | None:
        """Усиливает проверку поколения и делает цвет query-aware."""

        if generation_mismatch(
            canonical_title=canonical_title,
            candidate_title=candidate_title,
            requested_title=requested_title,
        ):
            return "model_number"

        reason = PriceService._model_mismatch_reason(
            canonical_title=canonical_title,
            candidate_title=candidate_title,
            requested_title=requested_title,
        )
        if (
            reason == "color"
            and requested_title is not None
            and requested_color_key(requested_title) is None
        ):
            return None
        return reason

    def _candidate_from_product(
        self,
        product: MasterCatalogProduct,
    ) -> ProductCandidate | None:
        if not product.offers:
            return None

        preferred_offer = next(
            (
                offer
                for offer in product.offers
                if offer.available and offer.url.strip()
            ),
            product.offers[0],
        )
        return ProductCandidate(
            key=f"{self._catalog_key_prefix}{product.key}",
            title=product.title,
            url=preferred_offer.url,
        )

    def _catalog_offers(
        self,
        product: MasterCatalogProduct,
        fresh_only: bool,
    ) -> list[ProductOffer]:
        now = datetime.now(timezone.utc)
        offers: list[ProductOffer] = []

        for item in product.offers:
            if (
                not item.available
                or item.price is None
                or not item.url.strip()
            ):
                continue
            if fresh_only and not self._is_fresh(item.updated_at, now):
                continue

            offers.append(
                ProductOffer(
                    source=item.source,
                    title=product.title,
                    price=float(item.price),
                    currency=item.currency or "BYN",
                    available=True,
                    url=item.url,
                    updated_at=self._format_updated_at(item.updated_at),
                )
            )

        return self._prepare_aggregate_offers(offers)

    def _catalog_comparison(
        self,
        product: MasterCatalogProduct,
        product_key: str,
        query: str,
        offers: list[ProductOffer],
        started: float,
    ) -> ComparisonResult:
        source_counts: dict[str, int] = {}
        for offer in offers:
            source_counts[offer.source] = source_counts.get(offer.source, 0) + 1

        statuses = [
            SourceSearchStatus(
                source=source,
                state="found",
                matched_offers=count,
                checked_candidates=count,
                duration_seconds=0.0,
            )
            for source, count in sorted(
                source_counts.items(),
                key=lambda item: item[0].casefold(),
            )
        ]

        return ComparisonResult(
            offers=offers,
            source_statuses=statuses,
            match_decisions=[],
            query=query,
            product_title=product.title,
            duration_seconds=time.monotonic() - started,
            completed_at=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            product_key=product_key,
            master_product_key=product.key,
            master_product_title=product.title,
            catalog_presentation=True,
        )

    def _select_live_candidate(
        self,
        canonical_title: str,
        candidates: list[ProductCandidate],
        requested_title: str | None = None,
    ) -> ProductCandidate | None:
        return next(
            (
                candidate
                for candidate in candidates
                if self._model_mismatch_reason(
                    canonical_title,
                    candidate.title,
                    requested_title=(
                        requested_title or canonical_title
                    ),
                )
                is None
            ),
            None,
        )

    def _remember_catalog_query(self, product_key: str, query: str) -> None:
        self._catalog_queries[product_key] = query
        self._catalog_queries.move_to_end(product_key)
        while len(self._catalog_queries) > self._catalog_query_cache_size:
            self._catalog_queries.popitem(last=False)

    def _is_fresh(self, updated_at: datetime, now: datetime) -> bool:
        value = updated_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return now - value.astimezone(timezone.utc) <= self._catalog_freshness

    @staticmethod
    def _format_updated_at(updated_at: datetime) -> str:
        value = updated_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone().strftime("%d.%m.%Y %H:%M")

    @classmethod
    def _freshness_hours_from_environment(cls) -> float:
        raw_value = os.getenv("MASTER_CATALOG_FRESHNESS_HOURS", "").strip()
        if not raw_value:
            return cls._default_freshness_hours
        try:
            value = float(raw_value)
        except ValueError:
            logger.warning(
                "Invalid MASTER_CATALOG_FRESHNESS_HOURS value: %r",
                raw_value,
            )
            return cls._default_freshness_hours
        return value if value > 0 else cls._default_freshness_hours
