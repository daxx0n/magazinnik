from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Iterable

from app.models.product import ProductCandidate
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.variant_matching import memory_signature


@dataclass(frozen=True, slots=True)
class PhoneCase:
    name: str
    query: str
    model_pattern: str
    forbidden_tokens: tuple[str, ...] = ()


CASES = (
    PhoneCase(
        name="huawei_nova_y63_6_128",
        query="Huawei nova Y63 6GB/128GB",
        model_pattern=r"\bhuawei\b.*\bnova\b.*\by63\b",
    ),
    PhoneCase(
        name="samsung_galaxy_a55_8_256",
        query="Samsung Galaxy A55 8GB/256GB",
        model_pattern=r"\bsamsung\b.*\bgalaxy\b.*\ba55\b",
    ),
    PhoneCase(
        name="apple_iphone_16_128",
        query="Apple iPhone 16 128GB",
        model_pattern=r"\b(?:apple\s+)?iphone\b.*\b16\b",
        forbidden_tokens=("16e", "plus", "pro", "max"),
    ),
    PhoneCase(
        name="xiaomi_redmi_note_14_pro_8_256",
        query="Xiaomi Redmi Note 14 Pro 8GB/256GB",
        model_pattern=r"\b(?:xiaomi\s+)?redmi\b.*\bnote\b.*\b14\b.*\bpro\b",
        forbidden_tokens=("pro plus",),
    ),
    PhoneCase(
        name="poco_x7_pro_12_512",
        query="Poco X7 Pro 12GB/512GB",
        model_pattern=r"\bpoco\b.*\bx7\b.*\bpro\b",
    ),
    PhoneCase(
        name="honor_x8c_8_256",
        query="Honor X8c 8GB/256GB",
        model_pattern=r"\bhonor\b.*\bx8c\b",
    ),
    PhoneCase(
        name="google_pixel_9_12_256",
        query="Google Pixel 9 12GB/256GB",
        model_pattern=r"\bgoogle\b.*\bpixel\b.*\b9\b",
        forbidden_tokens=("9a", "fold", "pro", "xl"),
    ),
    PhoneCase(
        name="samsung_galaxy_a17_8_256",
        query="Samsung Galaxy A17 8GB/256GB",
        model_pattern=r"\bsamsung\b.*\bgalaxy\b.*\ba17\b",
    ),
    PhoneCase(
        name="samsung_galaxy_a56_8_256",
        query="Samsung Galaxy A56 8GB/256GB",
        model_pattern=r"\bsamsung\b.*\bgalaxy\b.*\ba56\b",
    ),
    PhoneCase(
        name="apple_iphone_17_256",
        query="Apple iPhone 17 256GB",
        model_pattern=r"\b(?:apple\s+)?iphone\b.*\b17\b",
        forbidden_tokens=("air", "plus", "pro", "max"),
    ),
    PhoneCase(
        name="xiaomi_redmi_15c_4_128",
        query="Xiaomi Redmi 15C 4GB/128GB",
        model_pattern=r"\b(?:xiaomi\s+)?redmi\b.*\b15c\b",
    ),
    PhoneCase(
        name="honor_x6c_6_256",
        query="Honor X6c 6GB/256GB",
        model_pattern=r"\bhonor\b.*\bx6c\b",
    ),
    PhoneCase(
        name="tecno_spark_40_8_256",
        query="Tecno Spark 40 8GB/256GB",
        model_pattern=r"\btecno\b.*\bspark\b.*\b40\b",
        forbidden_tokens=("40c", "pro"),
    ),
    PhoneCase(
        name="huawei_pura_80_12_256",
        query="Huawei Pura 80 12GB/256GB",
        model_pattern=r"\bhuawei\b.*\bpura\b.*\b80\b",
        forbidden_tokens=("pro", "ultra"),
    ),
    PhoneCase(
        name="google_pixel_8_8_256",
        query="Google Pixel 8 8GB/256GB",
        model_pattern=r"\bgoogle\b.*\bpixel\b.*\b8\b",
        forbidden_tokens=("8a", "pro"),
    ),
)


class NoopCatalogService:
    async def ingest_offers_with_report_async(self, offers: Iterable[object]):
        items = list(offers)
        return SimpleNamespace(
            total_offers=len(items),
            created_products=0,
            merged_offers=0,
            updated_offers=0,
            product_keys=(),
        )


def normalize(value: str) -> str:
    normalized = value.casefold().replace("ё", "е")
    return " ".join(re.findall(r"[a-zа-я0-9]+", normalized))


def matching_candidates(
    case: PhoneCase,
    candidates: list[ProductCandidate],
) -> list[ProductCandidate]:
    expected_memory = memory_signature(case.query)
    selected: list[ProductCandidate] = []

    for candidate in candidates:
        normalized = normalize(candidate.title)
        if re.search(case.model_pattern, normalized, re.IGNORECASE) is None:
            continue
        if any(token in normalized for token in case.forbidden_tokens):
            continue
        if expected_memory and memory_signature(candidate.title) != expected_memory:
            continue
        selected.append(candidate)

    return selected


def result_summary(case: PhoneCase, candidate: ProductCandidate, result) -> dict:
    accepted_by_source: dict[str, list[str]] = {}
    rejected_reasons: dict[str, list[str]] = {}
    rejected_titles: dict[str, list[str]] = {}

    for decision in result.match_decisions:
        if decision.accepted:
            accepted_by_source.setdefault(decision.source, []).append(
                decision.title
            )
            continue
        rejected_reasons.setdefault(decision.source, []).append(decision.reason)
        rejected_titles.setdefault(decision.source, []).append(decision.title)

    return {
        "case": case.name,
        "query": case.query,
        "selected": candidate.title,
        "offers": [
            {
                "source": offer.source,
                "title": offer.title,
                "price": float(offer.price),
                "seller": offer.seller,
            }
            for offer in result.offers
        ],
        "statuses": {
            status.source: {
                "state": status.state,
                "matched": status.matched_offers,
                "checked": status.checked_candidates,
            }
            for status in result.source_statuses
        },
        "accepted_titles": {
            source: titles[:8]
            for source, titles in accepted_by_source.items()
        },
        "rejections": {
            source: {
                "reasons": sorted(set(reasons)),
                "titles": rejected_titles.get(source, [])[:5],
            }
            for source, reasons in rejected_reasons.items()
        },
    }


async def run_case(case: PhoneCase) -> dict:
    service = CatalogFirstPriceService(
        catalog_service=NoopCatalogService(),
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )

    try:
        candidates = await service.find_onliner_products(
            case.query,
            category="mobile",
        )
    except Exception as error:
        return {
            "case": case.name,
            "query": case.query,
            "error": f"onliner_search:{type(error).__name__}:{error}",
        }

    exact = matching_candidates(case, candidates)
    if not exact:
        return {
            "case": case.name,
            "query": case.query,
            "error": "selected_candidate_not_found",
            "onliner_candidates": [item.title for item in candidates[:10]],
        }

    candidate = exact[0]
    try:
        result = await service.search_all_sources_by_onliner_key(
            candidate.key,
            original_query=case.query,
        )
    except Exception as error:
        return {
            "case": case.name,
            "query": case.query,
            "selected": candidate.title,
            "error": f"aggregate:{type(error).__name__}:{error}",
        }

    return result_summary(case, candidate, result)


async def main() -> None:
    for case in CASES:
        summary = await run_case(case)
        print("PHONE_MATRIX " + json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
