from __future__ import annotations

import asyncio
import json

from app.services.catalog_first_search import CatalogFirstPriceService


async def main() -> None:
    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    products = await service.find_onliner_products("яндекс станция лайт 2 без часов")
    selected = next(
        product
        for product in products
        if product.key == "yndx00028blu"
        or (
            "без часов" in product.title.casefold()
            and "син" in product.title.casefold()
        )
    )
    result = await service.search_all_sources_by_onliner_key(selected.key)
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
        "accepted_clock_variant": any(
            "yndx-00026" in offer.title.casefold()
            or (
                "станция лайт 2" in offer.title.casefold()
                and "без часов" not in offer.title.casefold()
                and offer.source != "Onliner"
            )
            for offer in result.offers
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    required = {"21vek", "5 элемент", "Электросила"}
    found = {
        status.source
        for status in result.source_statuses
        if status.state == "found"
    }
    if not required.issubset(found) or payload["accepted_clock_variant"]:
        raise SystemExit(3)


if __name__ == "__main__":
    asyncio.run(main())
