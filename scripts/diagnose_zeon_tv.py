from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

import httpx

from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.price_service import PriceService
from app.sources.zeon import ZeonSource

PRODUCT_URL = (
    "https://www.zeon.by/product/"
    "1814419-xiaomi-tv-a-pro-50-2026-l50mb-apru-mezhdunarodnaya-versiya/"
)
QUERIES = (
    "xiaomi tv a pro 50",
    "Xiaomi TV A Pro 50 2026",
    "Xiaomi TV A Pro 50 2026 L50MB-APRU",
    'Xiaomi TV A Pro 50" 2026 L50MB-APRU',
    "L50MB-APRU",
)


async def download(
    source: ZeonSource,
    url: str,
    *,
    params: dict[str, str] | None = None,
) -> tuple[str, str, list[str]]:
    async with httpx.AsyncClient(
        headers=source._headers,
        timeout=source._timeout,
        follow_redirects=True,
    ) as client:
        response = await client.get(url, params=params)
        if source._is_verification_page(response.text):
            cookie = source._security_cookie_from_html(response.text)
            if cookie is not None:
                name, value = cookie
                client.cookies.set(name, value, domain="www.zeon.by", path="/")
                response = await client.get(url, params=params)
        response.raise_for_status()
        history = [str(item.url) for item in response.history]
        return response.text, str(response.url), history


async def main() -> None:
    source = ZeonSource()
    report: dict[str, object] = {"product_url": PRODUCT_URL, "searches": []}

    try:
        html, page_url, history = await download(source, PRODUCT_URL)
        report["direct"] = {
            "page_url": page_url,
            "history": history,
            "path": urlparse(page_url).path,
            "verification": source._is_verification_page(html),
            "offers": [
                {"title": item.title, "price": item.price, "url": item.url}
                for item in source._parse_page(html, page_url, 20)
            ],
        }
    except Exception as error:
        report["direct"] = {"error": f"{type(error).__name__}: {error}"}

    for query in QUERIES:
        try:
            html, page_url, history = await download(
                source,
                source._search_url,
                params={"q": query},
            )
            offers = source._parse_page(html, page_url, 100)
            report["searches"].append(
                {
                    "query": query,
                    "page_url": page_url,
                    "history": history,
                    "safe": source._is_safe_page_url(page_url),
                    "path": urlparse(page_url).path,
                    "catalog_cards": len(__import__("bs4").BeautifulSoup(html, "html.parser").select(".catalog-item")),
                    "title": (
                        __import__("bs4").BeautifulSoup(html, "html.parser").title.get_text(" ", strip=True)
                        if __import__("bs4").BeautifulSoup(html, "html.parser").title is not None
                        else None
                    ),
                    "offers": [
                        {"title": item.title, "price": item.price, "url": item.url}
                        for item in offers
                    ],
                }
            )
        except Exception as error:
            report["searches"].append(
                {"query": query, "error": f"{type(error).__name__}: {error}"}
            )

    service = CatalogFirstPriceService(
        catalog_search_enabled=False,
        catalog_presentation_enabled=False,
    )
    try:
        candidates = await service.find_onliner_products(
            "xiaomi tv a pro 50",
            category="tv",
        )
    except Exception as error:
        report["onliner"] = {"error": f"{type(error).__name__}: {error}"}
    else:
        report["onliner"] = [
            {"key": item.key, "title": item.title, "url": item.url}
            for item in candidates[:20]
        ]
        selected = next(
            (
                item
                for item in candidates
                if "tv a pro 50" in item.title.casefold()
            ),
            None,
        )
        if selected is not None:
            cross_query = PriceService._build_cross_source_query(selected.title)
            source_queries = PriceService._build_source_queries(
                query=cross_query,
                canonical_title=selected.title,
            )
            raw_offers = []
            for source_query in source_queries:
                try:
                    found = await source.find_offers(source_query, limit=100)
                except Exception as error:
                    raw_offers.append(
                        {"query": source_query, "error": f"{type(error).__name__}: {error}"}
                    )
                    continue
                raw_offers.append(
                    {
                        "query": source_query,
                        "offers": [
                            {
                                "title": item.title,
                                "url": item.url,
                                "reason": service._model_mismatch_reason(
                                    selected.title,
                                    item.title,
                                    requested_title=selected.title,
                                ),
                            }
                            for item in found
                        ],
                    }
                )
            report["bot_path"] = {
                "selected": selected.title,
                "cross_query": cross_query,
                "source_queries": source_queries,
                "results": raw_offers,
            }

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
