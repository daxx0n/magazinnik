from __future__ import annotations

import asyncio
import json

from app.services.catalog_first_search import CatalogFirstPriceService
from app.sources.twenty_one_vek import TwentyOneVekSource


CANONICAL = "LG NANO 4K UHD AI NU90 43NU900B6LA"
QUERIES = (
    CANONICAL,
    "43NU900B6LA",
    "LG 43NU900B6LA",
    "LG NU90 43NU900B6LA",
)


async def main() -> None:
    source = TwentyOneVekSource()
    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    rows: list[dict[str, object]] = []

    for query in QUERIES:
        try:
            offers = await source.find_offers(query, limit=20)
        except Exception as error:
            rows.append({
                "query": query,
                "error": f"{type(error).__name__}: {error}",
            })
            continue

        rows.append({
            "query": query,
            "offers": [
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
            ],
        })

    print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
