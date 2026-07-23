from __future__ import annotations

import asyncio
import json

from app.services.catalog_first_search import CatalogFirstPriceService
from app.sources.zeon import ZeonSource


CANONICAL_TITLE = (
    'Xiaomi TV A Pro 50" 2026 L50MB-APRU '
    '(международная версия)'
)


async def main() -> None:
    source = ZeonSource()
    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    report: dict[str, object] = {
        "query": CANONICAL_TITLE,
        "variants": source._query_variants(CANONICAL_TITLE),
    }

    try:
        offers = await source.find_offers(CANONICAL_TITLE, limit=20)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    else:
        report["offers"] = [
            {
                "title": item.title,
                "price": item.price,
                "url": item.url,
                "reason": service._model_mismatch_reason(
                    CANONICAL_TITLE,
                    item.title,
                    requested_title=CANONICAL_TITLE,
                ),
            }
            for item in offers
        ]

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
