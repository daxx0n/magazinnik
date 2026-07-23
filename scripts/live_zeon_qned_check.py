from __future__ import annotations

import asyncio
import json

from app.services.catalog_first_search import CatalogFirstPriceService
from app.sources.zeon import ZeonSource


CANONICAL = "LG QNED AI QNED70 50QNED70B6C"
EXPECTED_CODE = "50qned70b6c"
WRONG_CODE = "86qned70a6a"


async def main() -> None:
    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    source = ZeonSource()
    service._zeon_source = source

    offers = await service._search_zeon_query(
        query=CANONICAL,
        canonical_title=CANONICAL,
    )
    rows = []
    for offer in offers:
        reason = service._model_mismatch_reason(
            canonical_title=CANONICAL,
            candidate_title=offer.title,
            requested_title=CANONICAL,
        )
        rows.append(
            {
                "title": offer.title,
                "price": offer.price,
                "url": offer.url,
                "reason": reason,
            }
        )

    accepted = [row for row in rows if row["reason"] is None]
    report = {
        "canonical": CANONICAL,
        "query_variants": source._query_variants(CANONICAL),
        "offers": rows,
        "accepted": accepted,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if any(WRONG_CODE in row["title"].casefold() for row in accepted):
        raise SystemExit("Wrong 86QNED70A6A offer was accepted")
    if not any(EXPECTED_CODE in row["title"].casefold() for row in accepted):
        raise SystemExit("Exact 50QNED70B6C offer was not accepted")


if __name__ == "__main__":
    asyncio.run(main())
