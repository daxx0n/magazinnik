import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx


DEFAULT_PRODUCT_URL = (
    "https://catalog.onliner.by/mobile/apple/iphone17256bk"
)


def extract_product_key(product_url: str) -> str:
    """Получает ключ товара из последней части URL."""

    parsed_url = urlparse(product_url)

    if parsed_url.hostname != "catalog.onliner.by":
        raise ValueError(
            "Поддерживаются только ссылки catalog.onliner.by"
        )

    path_parts = [
        part
        for part in parsed_url.path.split("/")
        if part
    ]

    if len(path_parts) < 3:
        raise ValueError(
            "Ссылка не похожа на карточку товара Onliner"
        )

    return path_parts[-1]


async def main() -> None:
    product_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else DEFAULT_PRODUCT_URL
    )

    product_key = extract_product_key(product_url)

    endpoint = (
        "https://catalog.onliner.by/"
        f"sdapi/shop.api/products/{product_key}/positions"
    )

    headers = {
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": product_url,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),
    }

    print(f"Товар: {product_url}")
    print(f"Ключ: {product_key}")
    print(f"Endpoint: {endpoint}")
    print()

    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(endpoint)

    except httpx.RequestError as error:
        print(f"Ошибка подключения: {error}")
        return

    print(f"HTTP status: {response.status_code}")
    print(
        "Content-Type:",
        response.headers.get("content-type"),
    )
    print()

    try:
        data = response.json()
    except json.JSONDecodeError:
        print("Ответ не является JSON:")
        print(response.text[:3000])
        return

    output_path = Path("onliner_positions.json")

    output_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "Ответ сохранён в файл:",
        output_path.resolve(),
    )

    print()
    print("Начало ответа:")
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )[:5000]
    )


if __name__ == "__main__":
    asyncio.run(main())