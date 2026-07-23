from __future__ import annotations

import asyncio
import json

from app.services.catalog_first_search import CatalogFirstPriceService
from app.sources.twenty_one_vek import TwentyOneVekSource


CANONICAL = "LG NANO 4K UHD AI NU90 43NU900B6LA"
EXPECTED_CODE = "43nu900b6la"


async def main() -> None:
    source = TwentyOneVekSource()
    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )

    offers = await source.find_offers(CANONICAL, limit=20)
    rows = [
        {
            "title": offer.title,
            "price": offer.price,
            "url": offer.url,
            "reason": service._model_mismatch_reason(
                canonical_title=CANONICAL,
                candidate_title=offer.title,
                requested_title=CANONICAL,
            ),
        }
        for offer in offers
    ]
    accepted = [row for row in rows if row["reason"] is None]
    report = {
        "canonical": CANONICAL,
        "query_variants": source._query_variants(CANONICAL),
        "offers": rows,
        "accepted": accepted,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if not any(
        EXPECTED_CODE in str(row["title"]).casefold()
        for row in accepted
    ):
        raise SystemExit("Exact 43NU900B6LA offer was not accepted")


if __name__ == "__main__":
    asyncio.run(main())
