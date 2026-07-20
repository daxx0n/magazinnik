from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models.catalog import MasterCatalogProduct
from app.services.catalog_first_search import CatalogFirstPriceService


logger = logging.getLogger(__name__)
_MIN_TIME = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class CatalogRefreshConfig:
    """Настройки фонового обновления известных мастер-карточек."""

    enabled: bool = False
    interval_seconds: float = 3600.0
    initial_delay_seconds: float = 60.0
    batch_size: int = 10
    concurrency: int = 1

    @classmethod
    def from_environment(cls) -> CatalogRefreshConfig:
        return cls(
            enabled=_env_flag("CATALOG_REFRESH_ENABLED"),
            interval_seconds=_env_float(
                "CATALOG_REFRESH_INTERVAL_SECONDS",
                default=3600.0,
                minimum=300.0,
                maximum=86400.0,
            ),
            initial_delay_seconds=_env_float(
                "CATALOG_REFRESH_INITIAL_DELAY_SECONDS",
                default=60.0,
                minimum=0.0,
                maximum=3600.0,
            ),
            batch_size=_env_int(
                "CATALOG_REFRESH_BATCH_SIZE",
                default=10,
                minimum=1,
                maximum=100,
            ),
            concurrency=_env_int(
                "CATALOG_REFRESH_CONCURRENCY",
                default=1,
                minimum=1,
                maximum=3,
            ),
        )


@dataclass(frozen=True, slots=True)
class CatalogRefreshItem:
    """Результат обновления одной мастер-карточки."""

    product_key: str
    product_title: str
    state: str
    offer_count: int = 0
    duration_seconds: float = 0.0
    error: str = ""


@dataclass(frozen=True, slots=True)
class CatalogRefreshReport:
    """Сводка одного ограниченного цикла обновления каталога."""

    status: str
    started_at: datetime
    completed_at: datetime
    selected_products: int
    refreshed_products: int
    unchanged_products: int
    failed_products: int
    items: tuple[CatalogRefreshItem, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return max(
            (self.completed_at - self.started_at).total_seconds(),
            0.0,
        )


class CatalogRefreshService:
    """Обновляет самые старые карточки через существующий live-search."""

    def __init__(
        self,
        price_service: CatalogFirstPriceService,
        config: CatalogRefreshConfig | None = None,
    ) -> None:
        self._price_service = price_service
        self._catalog_service = price_service._catalog_service
        self._stale_after = price_service._catalog_freshness
        self._config = config or CatalogRefreshConfig.from_environment()
        self._lock = asyncio.Lock()
        self._last_report: CatalogRefreshReport | None = None

    @property
    def config(self) -> CatalogRefreshConfig:
        return self._config

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def last_report(self) -> CatalogRefreshReport | None:
        return self._last_report

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def stale_products(
        self,
        now: datetime | None = None,
    ) -> tuple[MasterCatalogProduct, ...]:
        """Возвращает карточки с наиболее старым обновлением первыми."""

        reference_time = _aware(now or datetime.now(timezone.utc))
        threshold = reference_time - self._stale_after
        candidates: list[tuple[datetime, MasterCatalogProduct]] = []

        for product in self._catalog_service.catalog.products:
            latest_update = self._latest_update(product)
            if latest_update < threshold:
                candidates.append((latest_update, product))

        candidates.sort(
            key=lambda pair: (
                pair[0],
                pair[1].title.casefold(),
                pair[1].key,
            )
        )
        return tuple(product for _, product in candidates)

    async def refresh_once(self) -> CatalogRefreshReport:
        """Обновляет ограниченный набор карточек без пересечения циклов."""

        if self._lock.locked():
            now = datetime.now(timezone.utc)
            report = CatalogRefreshReport(
                status="overlap_skipped",
                started_at=now,
                completed_at=now,
                selected_products=0,
                refreshed_products=0,
                unchanged_products=0,
                failed_products=0,
            )
            self._last_report = report
            return report

        async with self._lock:
            started_at = datetime.now(timezone.utc)
            products = self.stale_products(started_at)[
                : self._config.batch_size
            ]
            semaphore = asyncio.Semaphore(self._config.concurrency)

            async def refresh(
                product: MasterCatalogProduct,
            ) -> CatalogRefreshItem:
                async with semaphore:
                    return await self._refresh_product(product)

            items = tuple(
                await asyncio.gather(
                    *(refresh(product) for product in products)
                )
            )
            completed_at = datetime.now(timezone.utc)
            report = CatalogRefreshReport(
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                selected_products=len(products),
                refreshed_products=sum(
                    item.state == "refreshed" for item in items
                ),
                unchanged_products=sum(
                    item.state == "unchanged" for item in items
                ),
                failed_products=sum(
                    item.state == "failed" for item in items
                ),
                items=items,
            )
            self._last_report = report
            logger.info(
                "Catalog refresh completed: selected=%d refreshed=%d "
                "unchanged=%d failed=%d duration=%.3fs",
                report.selected_products,
                report.refreshed_products,
                report.unchanged_products,
                report.failed_products,
                report.duration_seconds,
            )
            return report

    async def run_forever(self) -> None:
        """Периодически запускает refresh, пока работает приложение."""

        if not self.enabled:
            logger.info("Catalog background refresh is disabled")
            return

        logger.info(
            "Catalog background refresh enabled: interval=%.0fs "
            "batch=%d concurrency=%d freshness=%.1fh",
            self._config.interval_seconds,
            self._config.batch_size,
            self._config.concurrency,
            self._stale_after.total_seconds() / 3600,
        )

        if self._config.initial_delay_seconds:
            await asyncio.sleep(self._config.initial_delay_seconds)

        while True:
            try:
                await self.refresh_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected catalog background refresh error")

            await asyncio.sleep(self._config.interval_seconds)

    async def _refresh_product(
        self,
        product: MasterCatalogProduct,
    ) -> CatalogRefreshItem:
        started = time.monotonic()
        previous_update = self._latest_update(product)

        try:
            result = await self._price_service.search_all_sources_by_onliner_key(
                f"catalog:{product.key}"
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning(
                "Catalog product refresh failed: product=%s error=%s",
                product.key,
                error,
            )
            return CatalogRefreshItem(
                product_key=product.key,
                product_title=product.title,
                state="failed",
                duration_seconds=time.monotonic() - started,
                error=f"{type(error).__name__}: {error}",
            )

        refreshed_product = self._product_by_key(product.key)
        current_update = (
            self._latest_update(refreshed_product)
            if refreshed_product is not None
            else previous_update
        )
        state = (
            "refreshed"
            if current_update > previous_update
            else "unchanged"
        )
        return CatalogRefreshItem(
            product_key=product.key,
            product_title=(
                refreshed_product.title
                if refreshed_product is not None
                else product.title
            ),
            state=state,
            offer_count=len(result.offers),
            duration_seconds=time.monotonic() - started,
        )

    def _product_by_key(
        self,
        product_key: str,
    ) -> MasterCatalogProduct | None:
        return next(
            (
                product
                for product in self._catalog_service.catalog.products
                if product.key == product_key
            ),
            None,
        )

    @staticmethod
    def _latest_update(product: MasterCatalogProduct) -> datetime:
        return max(
            (_aware(offer.updated_at) for offer in product.offers),
            default=_MIN_TIME,
        )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning("Invalid %s value: %r", name, raw_value)
        return default
    return min(max(value, minimum), maximum)


def _env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid %s value: %r", name, raw_value)
        return default
    return min(max(value, minimum), maximum)
