from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class MatchLevel(StrEnum):
    """Уровень уверенности сопоставления внешнего товара."""

    EXACT = "exact"
    PROBABLE = "probable"
    REVIEW = "review"
    REJECTED = "rejected"


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
