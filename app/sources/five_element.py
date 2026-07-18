import re
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.sources import (
    InvalidProductUrlError,
    ProductNotFoundError,
    SourceUnavailableError,
)


class FiveElementSource:
    """Получает товар с публичной страницы 5element.by."""

    source_name = "5 элемент"

    _search_endpoint = (
        "https://sort.diginetica.net/search"
    )

    _search_api_key = "08IE0509XQ"

    _search_strategy = (
        "advanced_xname,zero_queries"
    )
    _candidate_cache_size = 5_000

    _allowed_hosts = {
        "5element.by",
        "www.5element.by",
    }

    _headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    _timeout = httpx.Timeout(
        connect=10.0,
        read=20.0,
        write=10.0,
        pool=10.0,
    )

    def __init__(self) -> None:
        self._candidate_urls: OrderedDict[
            str,
            str,
        ] = OrderedDict()

    async def find_products(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        """Ищет карточки через поиск сайта 5element.by."""

        normalized_query = " ".join(
            query.strip().split()
        )

        if len(normalized_query) < 3:
            return []

        try:
            async with httpx.AsyncClient(
                headers={
                    **self._headers,
                    "Accept": "application/json",
                    "Referer": "https://5element.by/",
                },
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    self._search_endpoint,
                    params={
                        "st": normalized_query,
                        "apiKey": self._search_api_key,
                        "strategy": self._search_strategy,
                        "fullData": "true",
                        "withCorrection": "false",
                        "withFacets": "false",
                        "treeFacets": "true",
                        "regionId": "",
                        "useCategoryPrediction": "true",
                        "size": str(limit),
                        "offset": "0",
                        "showUnavailable": "true",
                        "unavailableMultiplier": "0.0002",
                        "withSku": "false",
                    },
                )

            response.raise_for_status()

        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "Поиск 5 элемента не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            raise SourceUnavailableError(
                "Поиск 5 элемента вернул HTTP-ошибку "
                f"{error.response.status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться "
                "к поиску 5 элемента."
            ) from error

        try:
            data = response.json()
        except ValueError as error:
            raise SourceUnavailableError(
                "Поиск 5 элемента вернул ответ "
                "в неожиданном формате."
            ) from error

        if not isinstance(data, dict):
            raise SourceUnavailableError(
                "Поиск 5 элемента вернул "
                "некорректный JSON."
            )

        raw_products = data.get("products", [])

        if not isinstance(raw_products, list):
            return []

        candidates: list[ProductCandidate] = []

        for raw_product in raw_products:
            candidate = self._parse_candidate(
                raw_product
            )

            if candidate is None:
                continue

            self._remember_candidate(candidate)
            candidates.append(candidate)

            if len(candidates) >= limit:
                break

        return candidates

    def _remember_candidate(
        self,
        candidate: ProductCandidate,
    ) -> None:
        """Хранит ограниченный индекс URL поисковых карточек."""

        self._candidate_urls[candidate.key] = candidate.url
        self._candidate_urls.move_to_end(candidate.key)

        while len(self._candidate_urls) > self._candidate_cache_size:
            self._candidate_urls.popitem(last=False)

    async def search_by_key(
        self,
        product_key: str,
    ) -> list[ProductOffer]:
        """Получает цену выбранной поисковой карточки."""

        product_url = self._candidate_urls.get(
            product_key
        )

        if product_url is None:
            raise ProductNotFoundError(
                "Карточка поиска 5 элемента устарела. "
                "Повтори поиск товара."
            )

        return await self.search(product_url)

    async def search(
        self,
        query: str,
    ) -> list[ProductOffer]:
        """Получает предложение по прямой ссылке."""

        product_url = self._validate_url(query)

        html = await self._download_page(
            product_url
        )

        offer = self._parse_product_page(
            html=html,
            product_url=product_url,
        )

        return [offer]

    @staticmethod
    def _parse_candidate(
        raw_product: object,
    ) -> ProductCandidate | None:
        """Преобразует результат Diginetica в карточку."""

        if not isinstance(raw_product, dict):
            return None

        product_id = raw_product.get("id")
        title = raw_product.get("name")
        link_url = raw_product.get("link_url")

        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                product_id,
                title,
                link_url,
            )
        ):
            return None

        if not link_url.startswith("/products/"):
            return None

        return ProductCandidate(
            key=product_id,
            title=title.strip(),
            url=(
                "https://5element.by"
                f"{link_url.rstrip('/')}"
            ),
        )

    def _validate_url(
        self,
        value: str,
    ) -> str:
        """Проверяет ссылку на товар 5element.by."""

        url = value.strip()
        parsed_url = urlparse(url)

        if parsed_url.scheme not in {
            "http",
            "https",
        }:
            raise InvalidProductUrlError(
                "Ссылка должна начинаться "
                "с http:// или https://."
            )

        if parsed_url.hostname not in (
            self._allowed_hosts
        ):
            raise InvalidProductUrlError(
                "Поддерживаются только ссылки "
                "5element.by."
            )

        if not parsed_url.path.startswith(
            "/products/"
        ):
            raise InvalidProductUrlError(
                "Ссылка не похожа на страницу "
                "товара 5 элемента."
            )

        clean_path = parsed_url.path.rstrip("/")

        return (
            "https://5element.by"
            f"{clean_path}"
        )

    async def _download_page(
        self,
        product_url: str,
    ) -> str:
        """Загружает страницу товара."""

        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    product_url
                )

            response.raise_for_status()

        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "5 элемент не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            status_code = (
                error.response.status_code
            )

            if status_code == 404:
                raise ProductNotFoundError(
                    "Страница товара "
                    "5 элемента не найдена."
                ) from error

            raise SourceUnavailableError(
                "5 элемент вернул HTTP-ошибку "
                f"{status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться "
                "к 5 элементу."
            ) from error

        return response.text

    def _parse_product_page(
        self,
        html: str,
        product_url: str,
    ) -> ProductOffer:
        """Извлекает название, цену и наличие."""

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        title = self._extract_title(soup)

        if not title:
            raise ProductNotFoundError(
                "Не удалось определить "
                "название товара."
            )

        price = self._extract_price(
            soup=soup,
            title=title,
        )

        if price is None:
            raise ProductNotFoundError(
                "Не удалось определить "
                "актуальную цену товара."
            )

        availability_text = (
            self._extract_availability(
                soup=soup,
                title=title,
            )
        )

        available = availability_text not in {
            "Нет в наличии",
            "Недоступен",
        }

        return ProductOffer(
            source=self.source_name,
            title=title,
            price=float(price),
            currency="BYN",
            available=available,
            url=product_url,
            seller="5 элемент",
            availability_text=availability_text,
            delivery_text=None,
            updated_at=datetime.now().strftime(
                "%d.%m.%Y %H:%M"
            ),
        )

    @staticmethod
    def _extract_title(
        soup: BeautifulSoup,
    ) -> str | None:
        """Получает название из заголовка h1."""

        heading = soup.find("h1")

        if heading:
            title = heading.get_text(
                separator=" ",
                strip=True,
            )

            if title:
                return title

        title_tag = soup.find("title")

        if title_tag:
            title = title_tag.get_text(
                separator=" ",
                strip=True,
            )

            if title:
                return title.split(
                    " купить ",
                    maxsplit=1,
                )[0].strip()

        return None

    def _extract_price(
        self,
        soup: BeautifulSoup,
        title: str,
    ) -> Decimal | None:
        """
        Получает полную текущую цену.

        Сначала проверяет структурированные
        HTML-атрибуты, затем использует
        текстовый блок возле названия товара.
        """

        structured_price = (
            self._extract_structured_price(
                soup
            )
        )

        if structured_price is not None:
            return structured_price

        page_text = soup.get_text(
            separator=" ",
            strip=True,
        )

        title_position = page_text.find(title)

        if title_position >= 0:
            relevant_text = page_text[
                title_position:
                title_position + 1500
            ]
        else:
            relevant_text = page_text[:3000]

        # Цена на странице имеет формат:
        # 3 199.00 или 3 199,00
        matches = re.findall(
            r"(?<!\d)"
            r"(\d{1,3}(?:[\s\xa0]\d{3})+"
            r"[.,]\d{2})"
            r"(?!\d)",
            relevant_text,
        )

        for raw_price in matches:
            price = self._parse_decimal(
                raw_price
            )

            if price is None:
                continue

            # Отсекаем ежемесячные платежи,
            # бонусы и случайные маленькие суммы.
            if price >= Decimal("20"):
                return price

        return None

    @staticmethod
    def _extract_structured_price(
        soup: BeautifulSoup,
    ) -> Decimal | None:
        """Проверяет стандартные price-атрибуты."""

        selectors = [
            ".p-head__order .p-price__actual",
            ".p-price__actual",
            '[itemprop="price"]',
            'meta[property="product:price:amount"]',
            'meta[name="price"]',
        ]

        for selector in selectors:
            element = soup.select_one(selector)

            if element is None:
                continue

            raw_value = (
                element.get("content")
                or element.get("value")
                or element.get_text(
                    separator=" ",
                    strip=True,
                )
            )

            price = (
                FiveElementSource
                ._parse_decimal(raw_value)
            )

            if price is not None:
                return price

        return None

    @staticmethod
    def _extract_availability(
        soup: BeautifulSoup,
        title: str,
    ) -> str:
        """Определяет статус наличия."""

        page_text = soup.get_text(
            separator=" ",
            strip=True,
        )

        title_position = page_text.find(title)

        if title_position >= 0:
            relevant_text = page_text[
                title_position:
                title_position + 4000
            ]
        else:
            relevant_text = page_text

        normalized_text = (
            relevant_text.casefold()
        )

        if "нет в наличии" in normalized_text:
            return "Нет в наличии"

        if "товар с витрины" in normalized_text:
            return "Товар с витрины"

        if "под заказ" in normalized_text:
            return "Под заказ"

        if "в наличии" in normalized_text:
            return "В наличии"

        if "в корзину" in normalized_text:
            return "Доступен к заказу"

        return "Наличие уточнить"

    @staticmethod
    def _parse_decimal(
        value: object,
    ) -> Decimal | None:
        """Преобразует строку цены в Decimal."""

        if value is None:
            return None

        normalized_value = (
            str(value)
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
        )

        normalized_value = re.sub(
            r"[^\d.]",
            "",
            normalized_value,
        )

        try:
            return Decimal(normalized_value)
        except InvalidOperation:
            return None
