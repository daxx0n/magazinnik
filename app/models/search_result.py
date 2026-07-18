from dataclasses import dataclass

from app.models.offer import ProductOffer


@dataclass(frozen=True, slots=True)
class SourceSearchStatus:
    """Итог проверки одного источника."""

    source: str
    state: str
    matched_offers: int = 0
    checked_candidates: int = 0
    duration_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class MatchDecision:
    """Решение о найденном кандидате магазина."""

    source: str
    title: str
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Предложения и отчёт по проверенным источникам."""

    offers: list[ProductOffer]
    source_statuses: list[SourceSearchStatus]
    match_decisions: list[MatchDecision]
    query: str = ""
    product_title: str = ""
    duration_seconds: float = 0.0
    completed_at: str = ""
    product_key: str = ""
