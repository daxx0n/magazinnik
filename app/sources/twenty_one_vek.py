import json
import re
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
        connect=20.0,
        read=45.0,
        write=20.0,
        pool=20.0,
    )

    _search_url = "https://www.21vek.by/search/"

    _query_token_pattern = re.compile(
        r"(?<![a-zа-я0-9])"
        r"[a-zа-я0-9]+(?:[-_/.][a-zа-я0-9]+)*"
        r"(?![a-zа-я0-9])",
        re.IGNORECASE,
    )
    _memory_pair_pattern = re.compile(
        r"\d{1,4}\s*(?:gb|tb|mb|гб|тб|мб)?\s*[/_-]\s*"
        r"\d{1,4}\s*(?:gb|tb|mb|гб|тб|мб)?",
        re.IGNORECASE,
    )
    _measurement_pattern = re.compile(
        r"\d+(?:gb|tb|mb|гб|тб|мб|hz|khz|mhz|ghz|"
        r"w|kw|v|mah|mp|g|k)",
        re.IGNORECASE,
    )
    _ignored_identifier_tokens = {
        "2sim", "3g", "4g", "5g", "4k", "8k", "esim", "lte",
    }
    _query_noise_words = {
        "ai", "lcd", "led", "microled", "miniled", "monitor",
        "nano", "nanocell", "neoqled", "oled", "qled", "qned",
        "smart", "television", "tv", "uhd", "монитор", "смарт",
        "телевизор",
    }

    @staticmethod
    def _compact_identifier(value: str) -> str:
        return re.sub(r"[^a-zа-я0-9]", "", value.casefold())

    @classmethod
    def _model_query_parts(
        cls,
        query: str,
    ) -> tuple[str | None, list[str], list[str]]:
        raw_tokens = cls._query_token_pattern.findall(query)
        brand: str | None = None
        family: list[str] = []
        strong: list[str] = []

        for raw_token in raw_tokens:
            token = raw_token.strip("._/-")
            compact = cls._compact_identifier(token)
            if not compact:
                continue

            if (
                brand is None
                and token.isalpha()
                and compact not in cls._query_noise_words
                and len(compact) >= 2
            ):
                brand = token

            if compact in cls._ignored_identifier_tokens:
                continue
            if cls._memory_pair_pattern.fullmatch(token) is not None:
                continue
            if cls._measurement_pattern.fullmatch(compact) is not None:
                continue
            if re.search(r"[a-zа-я]", compact) is None:
                continue
            if re.search(r"\d", compact) is None:
                continue

            has_separator = any(character in token for character in "-_/." )
            numeric_prefix_identifier = (
                token[0].isdigit()
                and len(compact) >= 5
                and sum(character.isdigit() for character in compact) >= 3
            )
            alpha_long_identifier = token[0].isalpha() and len(compact) >= 5
            if has_separator or numeric_prefix_identifier or alpha_long_identifier:
                strong.append(token)

            if not has_separator and 2 <= len(compact) <= 6:
                family.append(token)

        strong_compacts = {
            token: cls._compact_identifier(token) for token in strong
        }
        strong = [
            token
            for token in strong
            if not any(
                strong_compacts[token] != strong_compacts[other]
                and strong_compacts[token] in strong_compacts[other]
                for other in strong
            )
        ]

        def unique(values: list[str]) -> list[str]:
            result: list[str] = []
            seen: set[str] = set()
            for value in values:
                key = value.casefold()
                if key not in seen:
                    seen.add(key)
                    result.append(value)
            return result

        strong = unique(strong)
        strong_keys = {cls._compact_identifier(token) for token in strong}
        family = unique([
            token
            for token in family
            if cls._compact_identifier(token) not in strong_keys
        ])
        return brand, family, strong

    @classmethod
    def _query_variants(cls, query: str) -> list[str]:
        normalized = " ".join(query.strip().split())
        brand, family, strong = cls._model_query_parts(normalized)
        variants: list[str] = []
        seen: set[str] = set()

        def add(parts: list[str]) -> None:
            value = " ".join(part for part in parts if part).strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                variants.append(value)

        if strong:
            add([brand or "", *family, *strong])
            add([brand or "", *strong])
        add([normalized])
        return variants

    async def find_offers(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductOffer]:
        """Searches 21vek using compact model identity before broad text."""

        normalized_query = " ".join(query.strip().split())
        if len(normalized_query) < 3 or limit <= 0:
            return []

        variants = self._query_variants(normalized_query)
        _, _, strong = self._model_query_parts(normalized_query)
        strong_keys = [self._compact_identifier(token) for token in strong]
        unique_offers: dict[str, ProductOffer] = {}
        errors: list[SourceUnavailableError] = []

        for source_query in variants:
            try:
                offers = await self._find_offers_once(
                    source_query,
                    limit=max(limit, 20),
                )
            except SourceUnavailableError as error:
                errors.append(error)
                continue

            if strong_keys:
                exact = [
                    offer
                    for offer in offers
                    if any(
                        key in self._compact_identifier(offer.title)
                        for key in strong_keys
                    )
                ]
                if exact:
                    return exact[:limit]

            for offer in offers:
                unique_offers.setdefault(offer.url, offer)

        if unique_offers:
            return list(unique_offers.values())[:limit]
        if errors and len(errors) == len(variants):
            raise errors[0]
        return []

    async def _find_offers_once(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductOffer]:
        """Ищет доступные товары 21vek по названию."""

        normalized_query = " ".join(
            query.strip().split()
        )

        if len(normalized_query) < 3:
            return []

        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    self._search_url,
                    params={
                        "term": normalized_query,
                    },
                )

            response.raise_for_status()

        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "Поиск 21vek не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            raise SourceUnavailableError(
                "Поиск 21vek вернул HTTP-ошибку "
                f"{error.response.status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться "
                "к поиску 21vek."
            ) from error

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        next_data_element = soup.find(
            "script",
            id="__NEXT_DATA__",
        )

        if next_data_element is None:
            raise SourceUnavailableError(
                "21vek вернул страницу поиска "
                "в неожиданном формате."
            )

        raw_next_data = (
            next_data_element.string
            or next_data_element.get_text()
        )

        try:
            next_data = json.loads(raw_next_data)
            raw_initial_state = (
                next_data["props"]
                ["pageProps"]
                ["initialState"]
            )
            initial_state = json.loads(
                raw_initial_state
            )
            raw_products = (
                initial_state["searchResult"]
                ["products"]
                ["all"]
            )
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ) as error:
            raise SourceUnavailableError(
                "21vek вернул некорректные "
                "данные поиска."
            ) from error

        if not isinstance(raw_products, list):
            return []

        offers: list[ProductOffer] = []

        for raw_product in raw_products:
            offer = self._offer_from_search_result(
                raw_product
            )

            if offer is None:
                continue

            offers.append(offer)

            if len(offers) >= limit:
                break

        return offers

    def _offer_from_search_result(
        self,
        raw_product: object,
    ) -> ProductOffer | None:
        """Преобразует результат поиска в предложение."""

        if not isinstance(raw_product, dict):
            return None

        if raw_product.get("status") != "in":
            return None

        title = raw_product.get("name")
        link = raw_product.get("link")

        if not isinstance(title, str) or not title:
            return None

        if (
            not isinstance(link, str)
            or not link.startswith("/")
        ):
            return None

        price = self._parse_price(
            raw_product.get("salePrice")
            or raw_product.get("packPrice")
            or raw_product.get("price")
        )

        if price is None or price <= 0:
            return None

        return ProductOffer(
            source=self.source_name,
            title=title.strip(),
            price=float(price),
            currency="BYN",
            available=True,
            url=f"https://www.21vek.by{link}",
            seller="21vek",
            availability_text="В наличии",
            delivery_text=None,
            updated_at=datetime.now().strftime(
                "%d.%m.%Y %H:%M"
            ),
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

        transport = httpx.AsyncHTTPTransport(
            retries=2,
        )

        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=True,
                transport=transport,
            ) as client:
                response = await client.get(
                    product_url
                )

            response.raise_for_status()

        except httpx.ConnectTimeout as error:
            raise SourceUnavailableError(
                "Не удалось установить соединение "
                "с 21vek после нескольких попыток."
            ) from error

        except httpx.ReadTimeout as error:
            raise SourceUnavailableError(
                "21vek слишком долго передавал "
                "страницу товара."
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
