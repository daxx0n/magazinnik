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
    match_level: MatchLevel | None = None
    match_score: float | None = None
    match_reason: str | None = None
    match_conflicts: tuple[str, ...] = ()
    match_candidate_key: str | None = None
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


@dataclass(frozen=True, slots=True)
class MatchReview:
    """Спорное совпадение, требующее ручной проверки."""

    product_key: str
    product_title: str
    candidate_product_key: str
    candidate_product_title: str
    source: str
    external_id: str
    incoming_title: str
    score: float
    reason: str
    conflicts: tuple[str, ...] = ()
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True, slots=True)
class CatalogMetrics:
    """Снимок качества, дедупликации и свежести мастер-каталога."""

    product_count: int
    offer_count: int
    merged_offer_count: int
    duplicate_rate: float
    single_source_products: int
    multi_source_products: int
    exact_matches: int
    probable_matches: int
    review_matches: int
    rejected_matches: int
    fresh_offers: int
    stale_offers: int
    unavailable_offers: int
    source_offer_counts: tuple[tuple[str, int], ...] = ()

    @property
    def automatic_matches(self) -> int:
        return self.exact_matches + self.probable_matches

    @property
    def exact_share(self) -> float:
        if self.automatic_matches == 0:
            return 0.0
        return self.exact_matches / self.automatic_matches
