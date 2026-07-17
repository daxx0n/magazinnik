import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup


ROOT_DIR = Path(__file__).resolve().parents[1]

DEFAULT_URL = (
    "https://www.21vek.by/mobile/"
    "iphone17256gb_apple_10019135.html"
)

OUTPUT_DIR = ROOT_DIR / "data"
HTML_PATH = OUTPUT_DIR / "21vek_product.html"
JSON_PATH = OUTPUT_DIR / "21vek_diagnostics.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

PRICE_PATTERNS = [
    r"\d[\d\s\xa0]{0,12}[,.]\d{2}\s*(?:BYN|руб|р\.|Ҕ)",
    r"\d[\d\s\xa0]{0,12}\s*(?:BYN|руб|р\.|Ҕ)",
]

INTERESTING_WORDS = (
    "price",
    "cost",
    "offer",
    "availability",
    "stock",
    "product",
    "sale",
    "налич",
    "цен",
)


async def download_page(
    url: str,
) -> httpx.Response:
    """Загружает публичную страницу товара."""

    timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        response = await client.get(url)

    response.raise_for_status()

    return response


def extract_meta_tags(
    soup: BeautifulSoup,
) -> list[dict[str, str]]:
    """Собирает метатеги, связанные с товаром."""

    result: list[dict[str, str]] = []

    for tag in soup.find_all("meta"):
        name = str(
            tag.get("name")
            or tag.get("property")
            or tag.get("itemprop")
            or ""
        ).strip()

        content = str(
            tag.get("content")
            or ""
        ).strip()

        combined = f"{name} {content}".casefold()

        if not any(
            word in combined
            for word in INTERESTING_WORDS
        ):
            continue

        result.append(
            {
                "name": name,
                "content": content,
            }
        )

    return result


def try_parse_json(
    value: str,
) -> Any | None:
    """Пытается разобрать содержимое script как JSON."""

    value = value.strip()

    if not value:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def extract_json_scripts(
    soup: BeautifulSoup,
) -> list[dict[str, Any]]:
    """Собирает JSON из script-тегов."""

    result: list[dict[str, Any]] = []

    for number, script in enumerate(
        soup.find_all("script"),
        start=1,
    ):
        script_type = str(
            script.get("type")
            or ""
        ).casefold()

        script_id = str(
            script.get("id")
            or ""
        )

        content = script.string

        if not isinstance(content, str):
            content = script.get_text(
                separator=" ",
                strip=True,
            )

        parsed_json = try_parse_json(content)

        if parsed_json is not None:
            result.append(
                {
                    "number": number,
                    "id": script_id,
                    "type": script_type,
                    "json": parsed_json,
                }
            )
            continue

        normalized_content = content.casefold()

        if any(
            word in normalized_content
            for word in INTERESTING_WORDS
        ):
            result.append(
                {
                    "number": number,
                    "id": script_id,
                    "type": script_type,
                    "text_preview": content[:3000],
                }
            )

    return result


def extract_price_snippets(
    page_text: str,
) -> list[str]:
    """Ищет текстовые участки, похожие на цены."""

    snippets: list[str] = []
    used_snippets: set[str] = set()

    for pattern in PRICE_PATTERNS:
        for match in re.finditer(
            pattern,
            page_text,
            flags=re.IGNORECASE,
        ):
            start = max(
                match.start() - 150,
                0,
            )

            end = min(
                match.end() + 150,
                len(page_text),
            )

            snippet = " ".join(
                page_text[start:end].split()
            )

            if snippet in used_snippets:
                continue

            used_snippets.add(snippet)
            snippets.append(snippet)

            if len(snippets) >= 20:
                return snippets

    return snippets


def extract_attributes(
    soup: BeautifulSoup,
) -> list[dict[str, str]]:
    """Ищет HTML-атрибуты, связанные с ценой."""

    result: list[dict[str, str]] = []

    for element in soup.find_all(True):
        interesting_attributes: dict[str, str] = {}

        for attribute_name, attribute_value in (
            element.attrs.items()
        ):
            normalized_name = (
                str(attribute_name).casefold()
            )

            normalized_value = (
                " ".join(attribute_value)
                if isinstance(
                    attribute_value,
                    list,
                )
                else str(attribute_value)
            )

            combined = (
                f"{normalized_name} "
                f"{normalized_value}"
            ).casefold()

            if any(
                word in combined
                for word in INTERESTING_WORDS
            ):
                interesting_attributes[
                    normalized_name
                ] = normalized_value

        if not interesting_attributes:
            continue

        result.append(
            {
                "tag": element.name,
                **interesting_attributes,
                "text": element.get_text(
                    separator=" ",
                    strip=True,
                )[:300],
            }
        )

        if len(result) >= 100:
            break

    return result


def build_diagnostics(
    response: httpx.Response,
) -> dict[str, Any]:
    """Формирует диагностический JSON."""

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    heading = soup.find("h1")

    title_tag = soup.find("title")

    page_text = soup.get_text(
        separator=" ",
        strip=True,
    )

    return {
        "request": {
            "status_code": (
                response.status_code
            ),
            "requested_url": str(
                response.request.url
            ),
            "final_url": str(
                response.url
            ),
            "content_type": (
                response.headers.get(
                    "content-type"
                )
            ),
            "content_length": len(
                response.content
            ),
        },
        "page": {
            "h1": (
                heading.get_text(
                    separator=" ",
                    strip=True,
                )
                if heading
                else None
            ),
            "title": (
                title_tag.get_text(
                    separator=" ",
                    strip=True,
                )
                if title_tag
                else None
            ),
        },
        "meta_tags": extract_meta_tags(soup),
        "json_scripts": extract_json_scripts(
            soup
        ),
        "price_snippets": (
            extract_price_snippets(
                page_text
            )
        ),
        "interesting_attributes": (
            extract_attributes(soup)
        ),
    }


async def main() -> None:
    """Запускает диагностику карточки 21vek."""

    url = (
        sys.argv[1].strip()
        if len(sys.argv) > 1
        else DEFAULT_URL
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        response = await download_page(url)
    except httpx.HTTPError as error:
        print(
            "Ошибка загрузки страницы:",
            error,
        )
        raise SystemExit(1) from error

    HTML_PATH.write_text(
        response.text,
        encoding="utf-8",
    )

    diagnostics = build_diagnostics(
        response
    )

    JSON_PATH.write_text(
        json.dumps(
            diagnostics,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "Статус:",
        response.status_code,
    )

    print(
        "Итоговый URL:",
        response.url,
    )

    print(
        "Размер HTML:",
        len(response.content),
        "байт",
    )

    print(
        "H1:",
        diagnostics["page"]["h1"],
    )

    print(
        "JSON/script блоков:",
        len(
            diagnostics["json_scripts"]
        ),
    )

    print(
        "Фрагментов с ценой:",
        len(
            diagnostics["price_snippets"]
        ),
    )

    print()
    print(
        "HTML сохранён:",
        HTML_PATH,
    )

    print(
        "Диагностика сохранена:",
        JSON_PATH,
    )


if __name__ == "__main__":
    asyncio.run(main())