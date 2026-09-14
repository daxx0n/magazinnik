"""Source-independent local inventory and conservative, multi-source prices."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.models.catalog import ExternalCatalogItem
from app.models.product import ProductCandidate
from app.models.search_result import SourceSearchStatus
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.catalog_adapter import CatalogOfferAdapter
from app.services.catalog_relevance import (
    filter_catalog_candidates,
    is_catalog_record_relevant,
    is_iphone_phone_query,
)
from app.services.product_identity import ProductIdentityBuilder
from app.services.product_variants import extract_memory
from app.services.price_sanity import (
    filter_price_outliers,
    is_plausible_full_price,
)
from app.services.selection_presentation import selection_color_key
from app.services.variant_matching import sim_configuration
from app.sources import ProductNotFoundError, SourceUnavailableError

logger = logging.getLogger(__name__)

# Discovery queries, not a fabricated inventory of products or manufacturer colors.
DEFAULT_DISCOVERY_QUERIES = (
    "iPhone", "Samsung Galaxy", "Google Pixel", "Xiaomi", "Huawei", "Honor", "OnePlus", "Realme",
    "ноутбук", "планшет", "телевизор", "монитор", "видеокарта", "процессор",
    "материнская плата", "оперативная память", "SSD", "наушники", "колонка",
    "умные часы", "игровая консоль", "фотоаппарат", "принтер", "роутер",
    "холодильник", "стиральная машина", "посудомоечная машина", "пылесос",
    "духовой шкаф", "варочная панель", "микроволновая печь", "кофемашина",
    "кондиционер", "водонагреватель", "фен", "электробритва", "электроинструмент",
)


class UnifiedCatalogPriceService(CatalogFirstPriceService):
    def __init__(
        self,
        catalog_service,
        *,
        source_timeout=15.0,
        discovery_ttl=21600.0,
        inventory_ttl_days=30.0,
    ):
        super().__init__(catalog_service=catalog_service, catalog_search_enabled=True,
                         catalog_presentation_enabled=True, freshness_hours=0.25)
        self.source_timeout = source_timeout
        self.discovery_ttl = discovery_ttl
        self.inventory_ttl = timedelta(days=inventory_ttl_days)
        self._discovery_times = OrderedDict()
        self._requested_queries = OrderedDict()
        self._discovery_tasks = {}
        self._background_tasks = set()
        self._discovery_semaphore = asyncio.Semaphore(2)
        self._network_semaphore = asyncio.Semaphore(4)

    async def find_onliner_categories(self, query):
        # Do not gate the whole inventory on one retailer's category discovery.
        return []

    async def find_products(self, query, category=None):
        if category is not None:
            return await super().find_onliner_products(query, category)
        self._requested_queries[query] = None
        self._requested_queries.move_to_end(query)
        while len(self._requested_queries) > 500:
            self._requested_queries.popitem(last=False)
        products = await asyncio.to_thread(self._catalog_service.search, query)
        candidates = filter_catalog_candidates([
            candidate
            for product in products
            if (candidate := self._candidate_from_product(product)) is not None
        ], query)
        if is_iphone_phone_query(query):
            try:
                # A broad phone model list must represent every configured
                # source before it is shown, even when an older local hit
                # already exists from one retailer.
                await self.discover(query)
            except SourceUnavailableError:
                if not candidates:
                    raise
            products = await asyncio.to_thread(self._catalog_service.search, query)
            candidates = filter_catalog_candidates([
                candidate
                for product in products
                if (candidate := self._candidate_from_product(product))
                is not None
            ], query)
        elif not candidates:
            await self.discover(query)
            products = await asyncio.to_thread(self._catalog_service.search, query)
            candidates = filter_catalog_candidates([
                candidate
                for product in products
                if (candidate := self._candidate_from_product(product))
                is not None
            ], query)
        else:
            self._schedule_discovery(query)
        from app.services.model_selection import filter_products_by_query_generation
        return filter_products_by_query_generation(candidates, query)

    async def find_onliner_products(self, query, category=None):
        """Compatibility alias for callers predating the unified catalog."""

        return await self.find_products(query, category=category)

    def _candidate_from_product(self, product):
        now = datetime.now(timezone.utc)
        has_current_source = any(
            item.available
            and now - self._aware(item.updated_at) <= self.inventory_ttl
            for item in product.offers
        )
        if not has_current_source:
            return None
        return super()._candidate_from_product(product)

    @staticmethod
    def _aware(value):
        return value if value.tzinfo is not None else value.replace(
            tzinfo=timezone.utc
        )

    def _schedule_discovery(self, query):
        key = " ".join(query.casefold().split())
        if (
            key in self._discovery_tasks
            or time.monotonic() - self._discovery_times.get(
                key, float("-inf")
            ) < self.discovery_ttl
        ):
            return
        task = asyncio.create_task(self.discover(query))
        self._background_tasks.add(task)

        def done(completed):
            self._background_tasks.discard(completed)
            if completed.cancelled():
                return
            try:
                completed.result()
            except Exception:
                logger.exception(
                    "Catalog completion failed: query=%r", query
                )

        task.add_done_callback(done)

    async def _read_source(self, name, loader):
        try:
            async with self._network_semaphore:
                result = await asyncio.wait_for(loader(), timeout=self.source_timeout)
            return name, result, None
        except Exception as error:
            logger.warning("Catalog source unavailable: source=%s error=%s", name, error)
            return name, [], error

    def _offer_sources(self):
        return (("21vek", self._twenty_one_vek_source), ("Shop.by", self._shop_by_source),
                ("Электросила", self._electrosila_source), ("Zeon", self._zeon_source))

    async def discover(self, query):
        key = " ".join(query.casefold().split())
        if time.monotonic() - self._discovery_times.get(key, float("-inf")) < self.discovery_ttl:
            return
        task = self._discovery_tasks.get(key)
        if task is None:
            task = asyncio.create_task(self._discover(query, key))
            self._discovery_tasks[key] = task
            def done(completed):
                self._discovery_tasks.pop(key, None)
                if not completed.cancelled():
                    completed.exception()
            task.add_done_callback(done)
        return await asyncio.shield(task)

    async def _discover(self, query, key):
        async with self._discovery_semaphore:
            batches = await asyncio.gather(
                self._read_source("Onliner", lambda: self._onliner_source.find_products(query, limit=100)),
                self._read_source("5 элемент", lambda: self._five_element_source.find_products(query, limit=50)),
                *(self._read_source(name, lambda source=source: source.find_offers(query, limit=50))
                  for name, source in self._offer_sources()),
            )
            items = []
            builder, adapter = ProductIdentityBuilder(), CatalogOfferAdapter()
            for name, records, error in batches:
                for record in records:
                    if isinstance(record, ProductCandidate):
                        if not is_catalog_record_relevant(
                            query, record.title, record.url
                        ):
                            continue
                        items.append(ExternalCatalogItem(source=name, external_id=record.key,
                            title=record.title, url=record.url, identity=builder.build(record.title)))
                    elif (
                        record.available
                        and math.isfinite(float(record.price))
                        and record.price >= 0
                        and is_plausible_full_price(
                            record.title,
                            record.price,
                            record.currency,
                        )
                        and is_catalog_record_relevant(
                            query, record.title, record.url
                        )
                    ):
                        items.append(adapter.from_offer(record))
            if items:
                await asyncio.to_thread(self._catalog_service.ingest_external_items_with_report, items)
            if all(error is not None for _, _, error in batches):
                raise SourceUnavailableError("Все источники каталога временно недоступны.")
            retry_delay = min(300, self.discovery_ttl) if any(error is not None for _, _, error in batches) else self.discovery_ttl
            self._discovery_times[key] = time.monotonic() - self.discovery_ttl + retry_delay
            self._discovery_times.move_to_end(key)
            while len(self._discovery_times) > 1000:
                self._discovery_times.popitem(last=False)

    @staticmethod
    def _confirmed_variant(canonical, candidate):
        if not is_catalog_record_relevant(canonical, candidate):
            return False
        if CatalogFirstPriceService._model_mismatch_reason(canonical, candidate, requested_title=canonical) is not None:
            return False
        # Missing specifications are not confirmation of a selected variant.
        if sim_configuration(canonical) != sim_configuration(candidate):
            return False
        wanted_color = selection_color_key(canonical)
        if wanted_color is not None and wanted_color != selection_color_key(candidate):
            return False
        memory = extract_memory(canonical)
        return memory is None or memory == extract_memory(candidate)

    def _catalog_offers(self, product, fresh_only):
        verified = replace(product, offers=[item for item in product.offers
            if (
                self._confirmed_variant(product.title, item.title)
                and (
                    item.price is None
                    or is_plausible_full_price(
                        item.title,
                        item.price,
                        item.currency or "BYN",
                    )
                )
            )])
        offers = super()._catalog_offers(verified, fresh_only)
        return filter_price_outliers(offers)

    async def search_all_sources_by_onliner_key(self, product_key, original_query=None):
        if not product_key.startswith(self._catalog_key_prefix):
            return await super().search_all_sources_by_onliner_key(product_key, original_query)

        started = time.monotonic()
        product = await asyncio.to_thread(
            self._catalog_service.get_product,
            product_key.removeprefix(self._catalog_key_prefix),
        )
        if product is None:
            raise ProductNotFoundError("Карточка больше не существует. Повтори поиск.")

        async def onliner():
            known = next((item for item in product.offers
                          if item.source.casefold() == "onliner" and item.external_id), None)
            if known is not None:
                return await self._onliner_source.search_by_key(known.external_id)
            candidates = await self._onliner_source.find_products(product.title, limit=30)
            exact = next((item for item in candidates
                          if self._confirmed_variant(product.title, item.title)), None)
            return await self._onliner_source.search_by_key(exact.key) if exact else []

        async def five_element():
            known = next((item for item in product.offers
                          if item.source.casefold() in {"5 элемент", "5element"}
                          and item.external_id), None)
            if known is not None:
                return await self._five_element_source.search_by_key(known.external_id)
            candidates = await self._five_element_source.find_products(product.title, limit=30)
            exact = next((item for item in candidates
                          if self._confirmed_variant(product.title, item.title)), None)
            return await self._five_element_source.search_by_key(exact.key) if exact else []

        batches = await asyncio.gather(
            self._read_source("Onliner", onliner),
            self._read_source("5 элемент", five_element),
            *(self._read_source(name, lambda source=source: source.find_offers(product.title, limit=50))
              for name, source in self._offer_sources()),
        )
        verified, statuses, failed_sources = [], [], set()
        for name, candidates, error in batches:
            matches = [offer for offer in candidates
                       if offer.available and math.isfinite(float(offer.price))
                       and float(offer.price) >= 0
                       and is_plausible_full_price(
                           offer.title, offer.price, offer.currency
                       )
                       and self._confirmed_variant(product.title, offer.title)]
            verified.extend(matches)
            if error is not None:
                failed_sources.add(name.casefold())
            statuses.append(SourceSearchStatus(
                source=name,
                state="unavailable" if error else (
                    "found" if matches else ("filtered" if candidates else "not_found")
                ),
                matched_offers=len(matches),
                checked_candidates=len(candidates),
            ))

        verified = filter_price_outliers(verified)

        if verified:
            await self._catalog_service.ingest_offers_with_report_async(verified)

        # Cached prices are used only for sources that could not be reached.
        # Successful empty/filtered searches must not resurrect stale offers.
        all_failed = all(error is not None for _, _, error in batches)
        cached = []
        if not verified and all_failed:
            cached = [
                replace(
                    offer,
                    availability_text=(
                        "Сохранённая цена; источник сейчас недоступен"
                    ),
                )
                for offer in self._catalog_offers(product, fresh_only=False)
                if offer.source.casefold() in failed_sources
            ]
        offers = self._prepare_aggregate_offers([*verified, *cached])
        if not offers:
            raise ProductNotFoundError(
                "Подтверждённых предложений для выбранной комплектации не найдено."
            )

        result = self._catalog_comparison(
            product, product_key, original_query or product.title, offers, started,
        )
        return replace(result, source_statuses=statuses)

    async def close(self):
        tasks = [
            *self._discovery_tasks.values(),
            *self._background_tasks,
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run_discovery_loop(self, interval=60):
        configured = os.getenv("CATALOG_DISCOVERY_QUERIES", "")
        seeds = tuple(query.strip() for query in configured.split(";") if query.strip()) or DEFAULT_DISCOVERY_QUERIES
        cursor = 0
        await asyncio.sleep(5)
        while True:
            queries = list(dict.fromkeys((*seeds, *self._requested_queries)))
            query = queries[cursor % len(queries)]
            cursor += 1
            try:
                await self.discover(query)
            except Exception:
                logger.exception("Background catalog discovery failed: query=%r", query)
            await asyncio.sleep(max(30, interval))
