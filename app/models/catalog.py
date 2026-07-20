from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class MatchLevel(StrEnum):
    """Уровень уверенности сопоставления внешнего товара."""

    EXACT = "exact"
    PROBABLE = "probable"
    REVIEW = "review"
    REJECTED = "rejected"


class CatalogUpsertAction(StrEnum):
    """Результат добавления внешнего предложения в мастер-каталог."""

    CREATED = "created"
    MERGED = "merged"
    UPDATED = "updated"


@dataclass(frozen=True, slots=True)
class ProductIdentity:
    """Нормализованные признаки конкретной модификации товара."""

    brand: str | None
    model: str | None
    memory: str | None = None
    color: str | None = None
    revision: str | None = None
    ean: str | None = None
    mpn: str | None = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Объяснимый результат сопоставления двух товарных карточек."""

    level: MatchLevel
    score: float
    reason: str
    conflicts: tuple[str, ...] = ()


@dataclass(slots=True)
class ExternalCatalogItem:
    """Исходная карточка товара из конкретного магазина."""

    source: str
    external_id: str
    title: str
    url: str
    price: float | None = None
    currency: str | None = None
    available: bool = True
    identity: ProductIdentity | None = None
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(slots=True)
class MasterCatalogProduct:
    """Одна модификация товара и связанные предложения магазинов."""

    key: str
    title: str
    identity: ProductIdentity
    offers: list[ExternalCatalogItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CatalogUpsertResult:
    """Мастер-карточка и действие, выполненное при upsert."""

    product: MasterCatalogProduct
    action: CatalogUpsertAction


@dataclass(frozen=True, slots=True)
class CatalogIngestReport:
    """Сводка пакетной загрузки предложений в мастер-каталог."""

    total_offers: int
    created_products: int
    merged_offers: int
    updated_offers: int
    product_keys: tuple[str, ...] = ()
