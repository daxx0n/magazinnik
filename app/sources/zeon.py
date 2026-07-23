import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.offer import ProductOffer
from app.sources import SourceUnavailableError


class ZeonSource:
    """Ищет товары официального магазина Zeon."""

    source_name = "Zeon"

    _base_url = "https://www.zeon.by"
    _search_url = f"{_base_url}/search/"
    _allowed_hosts = {"zeon.by", "www.zeon.by"}

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
        connect=15.0,
        read=40.0,
        write=15.0,
        pool=15.0,
    )

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
        "2sim",
        "3g",
        "4g",
        "5g",
        "4k",
        "8k",
        "esim",
        "lte",
    }

    async def find_offers(
        self,
        query: str,
        limit: int = 20,
    ) -> list[ProductOffer]:
        """Возвращает доступные товары из поиска Zeon.

        Zeon часто не выполняет полнотекстовый поиск: длинный запрос может
        перенаправиться на общую категорию, а запрос по модельному коду — на
        точную карточку. Поэтому сильные идентификаторы проверяются первыми.
        """

        normalized_query = " ".join(query.strip().split())
        if len(normalized_query) < 3 or limit <= 0:
            return []

        priority_offers: dict[str, ProductOffer] = {}
        fallback_offers: dict[str, ProductOffer] = {}
        errors: list[SourceUnavailableError] = []
        variants = self._query_variants(normalized_query)

        for source_query, is_identifier in variants:
            try:
                html, page_url = await self._download_search_page(source_query)
            except SourceUnavailableError as error:
                errors.append(error)
                continue

            parsed = self._parse_page(
                html=html,
                page_url=page_url,
                limit=limit,
            )
            target = priority_offers if is_identifier else fallback_offers
            for offer in parsed:
                target.setdefault(offer.url, offer)

            if (
                is_identifier
                and parsed
                and urlparse(page_url).path.startswith("/product/")
            ):
                return sorted(parsed, key=lambda offer: offer.price)[:limit]

        ordered_priority = sorted(
            priority_offers.values(),
            key=lambda offer: offer.price,
        )
        ordered_fallback = sorted(
            (
                offer
                for url, offer in fallback_offers.items()
                if url not in priority_offers
            ),
            key=lambda offer: offer.price,
        )
        offers = [*ordered_priority, *ordered_fallback]
        if offers:
            return offers[:limit]

        if errors and len(errors) == len(variants):
            raise errors[0]
        return []

    @classmethod
    def _query_variants(cls, query: str) -> list[tuple[str, bool]]:
        """Строит точные модельные и совместимые полнотекстовые запросы."""

        normalized = " ".join(query.strip().split())
        variants: list[tuple[str, bool]] = []
        seen: set[str] = set()

        def add(value: str, is_identifier: bool) -> None:
            cleaned = " ".join(value.strip().split())
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                variants.append((cleaned, is_identifier))

        for identifier in cls._model_identifier_queries(normalized):
            add(identifier, True)

        add(normalized, False)
        without_inches = re.sub(r'["″”]+', " ", normalized)
        add(without_inches, False)
        return variants

    @classmethod
    def _model_identifier_queries(cls, query: str) -> list[str]:
        """Извлекает сильные коды модели, исключая память и характеристики."""

        identifiers: list[str] = []
        for raw_token in cls._query_token_pattern.findall(query):
            token = raw_token.strip("._/-")
            compact = re.sub(r"[^a-zа-я0-9]", "", token.casefold())
            if not compact:
                continue
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

            has_separator = any(character in token for character in "-_/.")
            starts_with_letter = token[0].isalpha()
            numeric_prefix_identifier = (
                not starts_with_letter
                and len(compact) >= 5
                and sum(character.isdigit() for character in compact) >= 3
            )
            if (
                not has_separator
                and not starts_with_letter
                and not numeric_prefix_identifier
            ):
                continue
            if len(compact) < 2:
                continue
            identifiers.append(token)

        ordered = sorted(
            dict.fromkeys(identifiers),
            key=lambda value: (
                any(character in value for character in "-_/."),
                len(re.sub(r"[^a-zа-я0-9]", "", value.casefold())),
            ),
            reverse=True,
        )
        compact_values = {
            value: re.sub(r"[^a-zа-я0-9]", "", value.casefold())
            for value in ordered
        }
        return [
            value
            for value in ordered
            if not any(
                compact_values[value] != compact_values[other]
                and compact_values[value] in compact_values[other]
                for other in ordered
            )
        ]

    async def _download_search_page(
        self,
        query: str,
    ) -> tuple[str, str]:
        """Проходит публичную JS-проверку и загружает выдачу."""

        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    self._search_url,
                    params={"q": query},
                )

                if self._is_verification_page(response.text):
                    security_cookie = self._security_cookie_from_html(
                        response.text
                    )
                    if security_cookie is None:
                        raise SourceUnavailableError(
                            "Zeon изменил формат проверки сайта."
                        )

                    cookie_name, cookie_value = security_cookie
                    client.cookies.set(
                        cookie_name,
                        cookie_value,
                        domain="www.zeon.by",
                        path="/",
                    )
                    response = await client.get(
                        self._search_url,
                        params={"q": query},
                    )

                response.raise_for_status()

                if self._is_verification_page(response.text):
                    raise SourceUnavailableError(
                        "Zeon не пропустил проверку сайта."
                    )

        except SourceUnavailableError:
            raise
        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "Поиск Zeon не ответил вовремя."
            ) from error
        except httpx.HTTPStatusError as error:
            raise SourceUnavailableError(
                "Поиск Zeon вернул HTTP-ошибку "
                f"{error.response.status_code}."
            ) from error
        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться к Zeon."
            ) from error

        page_url = str(response.url)
        if not self._is_safe_page_url(page_url):
            raise SourceUnavailableError(
                "Zeon перенаправил поиск на неизвестный адрес."
            )
        return response.text, page_url

    def _parse_page(
        self,
        html: str,
        page_url: str,
        limit: int,
    ) -> list[ProductOffer]:
        """Разбирает страницу поиска, категории либо точную карточку."""

        soup = BeautifulSoup(html, "html.parser")
        offers: dict[str, ProductOffer] = {}

        for card in soup.select(".catalog-item"):
            offer = self._parse_search_card(card)
            if offer is not None:
                offers.setdefault(offer.url, offer)
            if len(offers) >= limit:
                break

        if not offers and urlparse(page_url).path.startswith("/product/"):
            offer = self._parse_product_page(soup=soup, page_url=page_url)
            if offer is not None:
                offers[offer.url] = offer

        return sorted(offers.values(), key=lambda offer: offer.price)[:limit]

    def _parse_search_card(self, card) -> ProductOffer | None:
        title_element = card.select_one(".catalog-item-title a[href]")
        stock_element = card.select_one(".catalog-item-stock")
        club_price_element = card.select_one(".catalog-item-pricemini")
        regular_price_element = card.select_one(".catalog-item-price")

        if (
            title_element is None
            or stock_element is None
            or "instock" not in stock_element.get("class", [])
        ):
            return None

        title = " ".join(title_element.get_text(" ", strip=True).split())
        product_url = self._product_url(str(title_element.get("href", "")))
        price_element = (
            club_price_element
            if club_price_element is not None
            else regular_price_element
        )
        price = self._parse_decimal(
            price_element.get_text(" ", strip=True)
            if price_element is not None
            else None
        )

        if not title or product_url is None or price is None or price <= 0:
            return None

        delivery_text = " ".join(
            stock_element.get_text(" ", strip=True).split()
        ) or None
        availability_text = "В наличии"
        if club_price_element is not None:
            availability_text += "; цена с клубной картой"

        return self._offer(
            title=title,
            price=price,
            url=product_url,
            availability_text=availability_text,
            delivery_text=delivery_text,
        )

    def _parse_product_page(
        self,
        soup: BeautifulSoup,
        page_url: str,
    ) -> ProductOffer | None:
        title_element = soup.select_one('h1[itemprop="name"]')
        price_element = soup.select_one('meta[itemprop="price"][content]')
        availability_element = soup.select_one('[itemprop="availability"]')

        if (
            title_element is None
            or price_element is None
            or availability_element is None
        ):
            return None

        availability_url = str(
            availability_element.get("href", "")
        ).casefold()
        if not availability_url.endswith("instock"):
            return None

        title = " ".join(title_element.get_text(" ", strip=True).split())
        price = self._parse_decimal(price_element.get("content"))
        product_url = self._product_url(page_url)
        if (
            not title
            or price is None
            or price <= 0
            or product_url is None
        ):
            return None

        delivery_element = soup.select_one(
            "#delivery-tab-1 p strong.color-green"
        )
        delivery_text = (
            " ".join(
                delivery_element.get_text(" ", strip=True).split()
            )
            if delivery_element is not None
            else None
        )
        availability_text = "В наличии"
        if "С клубной картой" in soup.get_text(" "):
            availability_text += "; цена с клубной картой"

        return self._offer(
            title=title,
            price=price,
            url=product_url,
            availability_text=availability_text,
            delivery_text=delivery_text,
        )

    def _offer(
        self,
        *,
        title: str,
        price: Decimal,
        url: str,
        availability_text: str,
        delivery_text: str | None,
    ) -> ProductOffer:
        return ProductOffer(
            source=self.source_name,
            title=title,
            price=float(price),
            currency="BYN",
            available=True,
            url=url,
            seller=self.source_name,
            availability_text=availability_text,
            delivery_text=delivery_text,
            updated_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
        )

    def _product_url(self, raw_url: str) -> str | None:
        product_url = urljoin(self._base_url, raw_url)
        parsed = urlparse(product_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self._allowed_hosts
            or not parsed.path.startswith("/product/")
        ):
            return None
        return product_url

    def _is_safe_page_url(self, raw_url: str) -> bool:
        """Разрешает редиректы только внутри HTTPS-хостов Zeon."""

        parsed = urlparse(raw_url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in self._allowed_hosts
            and parsed.path.startswith("/")
        )

    @staticmethod
    def _is_verification_page(html: str) -> bool:
        return (
            "<title>Verification</title>" in html
            and "hg-security=" in html
        )

    @staticmethod
    def _security_cookie_from_html(
        html: str,
    ) -> tuple[str, str] | None:
        match = re.search(
            r'let\s+c="(hg-security)=([^;"\\]+)',
            html,
        )
        if match is None:
            return None
        return match.group(1), match.group(2)

    @staticmethod
    def _parse_decimal(value: object) -> Decimal | None:
        if value is None:
            return None

        normalized = re.sub(
            r"[^0-9,.]",
            "",
            str(value),
        ).replace(",", ".")
        if not normalized:
            return None

        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None
