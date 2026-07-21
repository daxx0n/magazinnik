from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import ComparisonResult, SourceSearchStatus


def _positive_environment_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


ANY_COLOR_MAX_CONCURRENCY = _positive_environment_int(
    "ANY_COLOR_MAX_CONCURRENCY",
    2,
)


async def load_any_color_results(
    products: Iterable[ProductCandidate],
    loader: Callable[[ProductCandidate], Awaitable[ComparisonResult | None]],
    *,
    max_concurrent: int | None = None,
) -> list[ComparisonResult]:
    """Loads color variants with bounded concurrency and preserves partial success."""

    limit = max_concurrent or ANY_COLOR_MAX_CONCURRENCY
    semaphore = asyncio.Semaphore(max(1, limit))

    async def run(product: ProductCandidate) -> ComparisonResult | None:
        async with semaphore:
            try:
                return await loader(product)
            except asyncio.CancelledError:
                raise
            except Exception:
                return None

    loaded = await asyncio.gather(*(run(product) for product in products))
    return [result for result in loaded if result is not None]


def aggregate_any_color_results(
    results: Iterable[ComparisonResult],
    *,
    original_query: str | None = None,
) -> ComparisonResult | None:
    """Combines all colors into one cheapest-first comparison."""

    successful = [result for result in results if result.offers]
    if not successful:
        return None

    offers_by_key: dict[tuple[str, str, str, str], ProductOffer] = {}
    for result in successful:
        for offer in result.offers:
            key = (
                offer.source.casefold().strip(),
                (offer.seller or "").casefold().strip(),
                offer.url.strip().rstrip("/"),
                offer.currency.casefold().strip(),
            )
            current = offers_by_key.get(key)
            if current is None or float(offer.price) < float(current.price):
                offers_by_key[key] = offer

    offers = sorted(
        offers_by_key.values(),
        key=lambda offer: (
            float(offer.price),
            offer.source.casefold(),
            (offer.seller or "").casefold(),
            offer.title.casefold(),
        ),
    )
    cheapest = min(
        successful,
        key=lambda result: min(float(offer.price) for offer in result.offers),
    )

    statuses = _merge_source_statuses(successful)
    decisions = []
    seen_decisions: set[tuple[str, str, bool, str]] = set()
    for result in successful:
        for decision in result.match_decisions:
            key = (
                decision.source,
                decision.title,
                decision.accepted,
                decision.reason,
            )
            if key not in seen_decisions:
                seen_decisions.add(key)
                decisions.append(decision)

    return replace(
        cheapest,
        offers=offers,
        source_statuses=statuses,
        match_decisions=decisions,
        query=original_query or cheapest.query,
        duration_seconds=max(
            (result.duration_seconds for result in successful),
            default=0.0,
        ),
    )


def _merge_source_statuses(
    results: Iterable[ComparisonResult],
) -> list[SourceSearchStatus]:
    grouped: dict[str, list[SourceSearchStatus]] = {}
    display_names: dict[str, str] = {}

    for result in results:
        for status in result.source_statuses:
            key = status.source.casefold().strip()
            grouped.setdefault(key, []).append(status)
            display_names.setdefault(key, status.source)

    state_priority = {
        "found": 4,
        "filtered": 3,
        "not_found": 2,
        "unavailable": 1,
    }
    merged: list[SourceSearchStatus] = []
    for key in sorted(grouped):
        statuses = grouped[key]
        best = max(
            statuses,
            key=lambda status: state_priority.get(status.state, 0),
        )
        merged.append(
            SourceSearchStatus(
                source=display_names[key],
                state=best.state,
                matched_offers=sum(status.matched_offers for status in statuses),
                checked_candidates=sum(
                    status.checked_candidates for status in statuses
                ),
                duration_seconds=max(
                    (status.duration_seconds for status in statuses),
                    default=0.0,
                ),
            )
        )
    return merged
