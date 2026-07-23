from __future__ import annotations

import asyncio
import json

from app.services.catalog_first_search import CatalogFirstPriceService


QUERY = "яндекс станция лайт 2"
SOURCES = ("5 элемент", "21vek", "Электросила")


async def main() -> None:
    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    products = await service.find_onliner_products(QUERY)
    selected = [
        product
        for product in products
        if "станция" in product.title.casefold()
        and "лайт" in product.title.casefold()
        and "2" in product.title
    ]

    result: dict[str, object] = {
        "query": QUERY,
        "onliner": [
            {"key": product.key, "title": product.title}
            for product in selected
        ],
        "sources": {},
    }

    source_rows: dict[str, list[dict[str, object]]] = {}
    canonical_titles = [product.title for product in selected]
    if not canonical_titles:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    cross_query = service._build_cross_source_query(canonical_titles[0])
    result["cross_query"] = cross_query
    result["source_queries"] = service._build_source_queries(
        query=cross_query,
        canonical_title=canonical_titles[0],
    )

    five_products = []
    twenty_offers = []
    electro_offers = []
    for source_query in result["source_queries"]:
        five_products.extend(
            await service._five_element_source.find_products(
                query=source_query,
                limit=100,
            )
        )
        twenty_offers.extend(
            await service._twenty_one_vek_source.find_offers(
                query=source_query,
                limit=100,
            )
        )
        electro_offers.extend(
            await service._electrosila_source.find_offers(
                query=source_query,
                limit=30,
            )
        )

    raw_items = {
        "5 элемент": five_products,
        "21vek": twenty_offers,
        "Электросила": electro_offers,
    }

    for source_name in SOURCES:
        seen: set[str] = set()
        rows: list[dict[str, object]] = []
        for item in raw_items[source_name]:
            identity = getattr(item, "key", None) or getattr(item, "url", "")
            if identity in seen:
                continue
            seen.add(identity)
            title = item.title
            reasons = {
                canonical: service._model_mismatch_reason(
                    canonical_title=canonical,
                    candidate_title=title,
                    requested_title=canonical,
                )
                for canonical in canonical_titles
            }
            rows.append(
                {
                    "title": title,
                    "url": getattr(item, "url", ""),
                    "price": getattr(item, "price", None),
                    "reasons": reasons,
                }
            )
        source_rows[source_name] = rows

    result["sources"] = source_rows
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
