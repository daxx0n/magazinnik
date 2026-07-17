import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.offer import ProductOffer
from app.sources import (
    InvalidProductUrlError,
    ProductNotFoundError,
    SourceUnavailableError,
)


class TwentyOneVekSource:
    """Получает товар с публичной карточки 21vek.by."""

    source_name = "21vek"

    _allowed_hosts = {
        "21vek.by",
        "www.21vek.by",
    }

    _headers = {
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

    _timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

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

    def _validate_url(
        self,
        value: str,
    ) -> str:
        """Проверяет ссылку на карточку 21vek."""

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
                "21vek.by."
            )

        path = parsed_url.path.rstrip("/")

        if not path.endswith(".html"):
            raise InvalidProductUrlError(
                "Ссылка не похожа на карточку "
                "товара 21vek."
            )

        return f"https://www.21vek.by{path}"

    async def _download_page(
        self,
        product_url: str,
    ) -> str:
        """Загружает HTML карточки товара."""

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
                "21vek не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            status_code = (
                error.response.status_code
            )

            if status_code == 404:
                raise ProductNotFoundError(
                    "Страница товара 21vek "
                    "не найдена."
                ) from error

            raise SourceUnavailableError(
                "21vek вернул HTTP-ошибку "
                f"{status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться "
                "к 21vek."
            ) from error

        return response.text

    def _parse_product_page(
        self,
        html: str,
        product_url: str,
    ) -> ProductOffer:
        """Извлекает данные товара из HTML."""

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        product_data = (
            self._extract_product_json_ld(
                soup
            )
        )

        if product_data is not None:
            return self._offer_from_json_ld(
                product_data=product_data,
                fallback_url=product_url,
            )

        next_product_data = (
            self._extract_next_product_data(
                soup
            )
        )

        if next_product_data is not None:
            return self._offer_from_next_data(
                product_data=next_product_data,
                fallback_url=product_url,
            )

        raise ProductNotFoundError(
            "На странице 21vek не найдены "
            "структурированные данные товара."
        )

    def _extract_product_json_ld(
        self,
        soup: BeautifulSoup,
    ) -> dict[str, Any] | None:
        """Ищет объект schema.org Product."""

        scripts = soup.find_all(
            "script",
            attrs={
                "type": "application/ld+json",
            },
        )

        for script in scripts:
            content = (
                script.string
                or script.get_text(
                    separator=" ",
                    strip=True,
                )
            )

            if not content:
                continue

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                continue

            product = self._find_product_object(
                data
            )

            if product is not None:
                return product

        return None

    def _find_product_object(
        self,
        value: Any,
    ) -> dict[str, Any] | None:
        """Рекурсивно ищет объект Product."""

        if isinstance(value, list):
            for item in value:
                product = (
                    self._find_product_object(
                        item
                    )
                )

                if product is not None:
                    return product

            return None

        if not isinstance(value, dict):
            return None

        object_type = value.get("@type")

        if (
            object_type == "Product"
            or (
                isinstance(
                    object_type,
                    list,
                )
                and "Product" in object_type
            )
        ):
            return value

        graph = value.get("@graph")

        if graph is not None:
            return self._find_product_object(
                graph
            )

        return None

    def _offer_from_json_ld(
        self,
        product_data: dict[str, Any],
        fallback_url: str,
    ) -> ProductOffer:
        """Создаёт предложение из JSON-LD."""

        title = product_data.get("name")

        if not isinstance(title, str):
            raise ProductNotFoundError(
                "21vek не вернул название товара."
            )

        raw_offers = product_data.get("offers")

        offer_data = self._select_offer(
            raw_offers
        )

        if offer_data is None:
            raise ProductNotFoundError(
                "21vek не вернул цену товара."
            )

        price = self._parse_price(
            offer_data.get("price")
        )

        if price is None:
            price = self._parse_price(
                offer_data.get("lowPrice")
            )

        if price is None:
            raise ProductNotFoundError(
                "Не удалось определить "
                "цену товара 21vek."
            )

        currency = offer_data.get(
            "priceCurrency",
            "BYN",
        )

        if not isinstance(currency, str):
            currency = "BYN"

        availability_value = str(
            offer_data.get(
                "availability",
                "",
            )
        )

        (
            available,
            availability_text,
        ) = self._parse_availability(
            availability_value
        )

        offer_url = offer_data.get("url")

        if not isinstance(offer_url, str):
            offer_url = fallback_url

        return ProductOffer(
            source=self.source_name,
            title=title.strip(),
            price=float(price),
            currency=currency.upper(),
            available=available,
            url=offer_url,
            seller="21vek",
            availability_text=(
                availability_text
            ),
            delivery_text=None,
            updated_at=datetime.now().strftime(
                "%d.%m.%Y %H:%M"
            ),
        )

    @staticmethod
    def _select_offer(
        raw_offers: Any,
    ) -> dict[str, Any] | None:
        """Выбирает подходящее предложение."""

        if isinstance(raw_offers, dict):
            return raw_offers

        if not isinstance(raw_offers, list):
            return None

        offers = [
            offer
            for offer in raw_offers
            if isinstance(offer, dict)
        ]

        if not offers:
            return None

        for offer in offers:
            availability = str(
                offer.get(
                    "availability",
                    "",
                )
            )

            if availability.endswith(
                "/InStock"
            ):
                return offer

        return offers[0]

    def _extract_next_product_data(
        self,
        soup: BeautifulSoup,
    ) -> dict[str, Any] | None:
        """Получает товар из __NEXT_DATA__."""

        script = soup.find(
            "script",
            id="__NEXT_DATA__",
        )

        if script is None:
            return None

        content = (
            script.string
            or script.get_text(
                separator=" ",
                strip=True,
            )
        )

        if not content:
            return None

        try:
            next_data = json.loads(content)
        except json.JSONDecodeError:
            return None

        try:
            initial_state_raw = (
                next_data["props"]
                ["pageProps"]
                ["initialState"]
            )
        except (
            KeyError,
            TypeError,
        ):
            return None

        if isinstance(
            initial_state_raw,
            str,
        ):
            try:
                initial_state = json.loads(
                    initial_state_raw
                )
            except json.JSONDecodeError:
                return None
        elif isinstance(
            initial_state_raw,
            dict,
        ):
            initial_state = initial_state_raw
        else:
            return None

        try:
            product_data = (
                initial_state
                ["productCard"]
                ["fullProductData"]
            )
        except (
            KeyError,
            TypeError,
        ):
            return None

        if not isinstance(
            product_data,
            dict,
        ):
            return None

        return product_data

    def _offer_from_next_data(
        self,
        product_data: dict[str, Any],
        fallback_url: str,
    ) -> ProductOffer:
        """Создаёт предложение из Next.js state."""

        title = product_data.get("name")

        if not isinstance(title, str):
            raise ProductNotFoundError(
                "21vek не вернул название товара."
            )

        prices = product_data.get(
            "prices",
            {},
        )

        if not isinstance(prices, dict):
            prices = {}

        price = self._parse_price(
            prices.get("salePrice")
        )

        if price is None or price <= 0:
            price = self._parse_price(
                prices.get("price")
            )

        if price is None or price <= 0:
            raise ProductNotFoundError(
                "Не удалось определить "
                "цену товара 21vek."
            )

        status = str(
            product_data.get(
                "status",
                "",
            )
        ).casefold()

        available = status == "in"

        availability_text = (
            "В наличии"
            if available
            else "Нет в наличии"
        )

        product_link = product_data.get(
            "link"
        )

        if (
            isinstance(product_link, str)
            and product_link.startswith("/")
        ):
            offer_url = (
                "https://www.21vek.by"
                f"{product_link}"
            )
        else:
            offer_url = fallback_url

        return ProductOffer(
            source=self.source_name,
            title=title.strip(),
            price=float(price),
            currency="BYN",
            available=available,
            url=offer_url,
            seller="21vek",
            availability_text=(
                availability_text
            ),
            delivery_text=None,
            updated_at=datetime.now().strftime(
                "%d.%m.%Y %H:%M"
            ),
        )

    @staticmethod
    def _parse_availability(
        value: str,
    ) -> tuple[bool, str]:
        """Преобразует schema.org availability."""

        availability_code = (
            value.rstrip("/")
            .rsplit("/", maxsplit=1)[-1]
            .casefold()
        )

        availability_map = {
            "instock": (
                True,
                "В наличии",
            ),
            "limitedavailability": (
                True,
                "Ограниченное количество",
            ),
            "backorder": (
                True,
                "Под заказ",
            ),
            "preorder": (
                True,
                "Предзаказ",
            ),
            "outofstock": (
                False,
                "Нет в наличии",
            ),
            "discontinued": (
                False,
                "Снят с продажи",
            ),
            "soldout": (
                False,
                "Продан",
            ),
        }

        return availability_map.get(
            availability_code,
            (
                True,
                "Наличие уточнить",
            ),
        )

    @staticmethod
    def _parse_price(
        value: Any,
    ) -> Decimal | None:
        """Преобразует цену в Decimal."""

        if value is None:
            return None

        normalized_value = (
            str(value)
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
        )

        try:
            return Decimal(
                normalized_value
            )
        except InvalidOperation:
            return None