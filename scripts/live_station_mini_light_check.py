from __future__ import annotations

import asyncio
import json

from app.services.catalog_first_search import CatalogFirstPriceService


QUERY = "яндекс станция лайт 2 без часов"


async def main() -> None:
    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    products = await service.find_onliner_products(QUERY)
    selected = next(
        product
        for product in products
        if (
            product.key == "yndx00028blu"
            or (
                "лайт" in product.title.casefold()
                and "2" in product.title
                and "без часов" in product.title.casefold()
            )
        )
    )
    result = await service.search_all_sources_by_onliner_key(
        selected.key,
        original_query=QUERY,
    )

    wrong_offers = [
        offer
        for offer in result.offers
        if "мини" in offer.title.casefold()
        or " mini " in f" {offer.title.casefold()} "
    ]
    wrong_accepted_decisions = [
        decision
        for decision in result.match_decisions
        if decision.accepted
        and (
            "мини" in decision.title.casefold()
            or " mini " in f" {decision.title.casefold()} "
        )
    ]
    rejected_mini = [
        {
            "source": decision.source,
            "title": decision.title,
            "reason": decision.reason,
        }
        for decision in result.match_decisions
        if not decision.accepted
        and (
            "мини" in decision.title.casefold()
            or " mini " in f" {decision.title.casefold()} "
        )
    ]

    payload = {
        "selected": {"key": selected.key, "title": selected.title},
        "offers": [
            {
                "source": offer.source,
                "title": offer.title,
                "price": offer.price,
                "url": offer.url,
            }
            for offer in result.offers
        ],
        "statuses": [
            {
                "source": status.source,
                "state": status.state,
                "matched": status.matched_offers,
                "checked": status.checked_candidates,
            }
            for status in result.source_statuses
        ],
        "rejected_mini": rejected_mini,
        "wrong_offers": [offer.title for offer in wrong_offers],
        "wrong_accepted_decisions": [
            decision.title for decision in wrong_accepted_decisions
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))

    if wrong_offers or wrong_accepted_decisions:
        raise SystemExit(3)
    if rejected_mini and any(
        item["reason"] != "version" for item in rejected_mini
    ):
        raise SystemExit(4)


if __name__ == "__main__":
    asyncio.run(main())
