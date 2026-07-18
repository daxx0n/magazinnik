import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.offer import ProductOffer
from app.sources import SourceUnavailableError


class ElectrosilaSource:
    """Ищет товары официального магазина «Электросила»."""

    source_name = "Электросила"

    _base_url = "https://sila.by"
    _search_url = f"{_base_url}/search"
    _allowed_hosts = {"sila.by", "www.sila.by"}

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

    async def find_offers(
        self,
        query: str,
        limit: int = 100,
    ) -> list[ProductOffer]:
        """Возвращает доступные товары из поисковой выдачи."""

        normalized_query = " ".join(query.strip().split())

        if len(normalized_query) < 3 or limit <= 0:
            return []

        pages = await self._download_search_pages(
            query=normalized_query,
            limit=limit,
        )
        offers: dict[str, ProductOffer] = {}

        for html in pages:
            for offer in self._parse_search_results(
                html=html,
                limit=limit,
            ):
                previous = offers.get(offer.url)

                if previous is None or offer.price < previous.price:
                    offers[offer.url] = offer

            if len(offers) >= limit:
                break

        return sorted(
            offers.values(),
            key=lambda offer: offer.price,
        )[:limit]

    async def _download_search_pages(
        self,
        query: str,
        limit: int,
    ) -> list[str]:
        """Загружает выдачу, сохраняя кодировку формы сайта."""

        form_data = {
            "autofind_on": "1",
            "find_param": "",
            "action": "0",
            "point": "0",
            "num_row": "0",
            "group": "0",
            "find": query,
        }
        encoded_form = urlencode(
            form_data,
            encoding="cp1251",
        ).encode("ascii")
        pages: list[str] = []
        next_url: str | None = None
        seen_urls: set[str] = set()
        found_cards = 0

        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    self._search_url,
                    content=encoded_form,
                    headers={
                        "Content-Type": (
                            "application/x-www-form-urlencoded"
                        )
                    },
                )

                while True:
                    response.raise_for_status()
                    html = self._decode_response(response)
                    pages.append(html)
                    soup = BeautifulSoup(html, "html.parser")
                    found_cards += len(
                        soup.select(".tov_prew_search")
                    )

                    if found_cards >= limit:
                        break

                    next_url = self._next_page_url(soup)

                    if (
                        next_url is None
                        or next_url in seen_urls
                    ):
                        break

                    seen_urls.add(next_url)
                    response = await client.get(next_url)

        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "Поиск Электросилы не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            raise SourceUnavailableError(
                "Поиск Электросилы вернул HTTP-ошибку "
                f"{error.response.status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться к Электросиле."
            ) from error

        return pages

    def _parse_search_results(
        self,
        html: str,
        limit: int,
    ) -> list[ProductOffer]:
        """Разбирает карточки товаров поисковой выдачи."""

        soup = BeautifulSoup(html, "html.parser")
        offers: list[ProductOffer] = []

        for card in soup.select(".tov_prew_search"):
            offer = self._parse_offer_card(card)

            if offer is not None:
                offers.append(offer)

            if len(offers) >= limit:
                break

        return offers

    def _parse_offer_card(self, card) -> ProductOffer | None:
        """Преобразует одну карточку Электросилы."""

        link_element = card.select_one(
            'a[href] img[alt]'
        )
        price_element = card.select_one(".price")
        buy_element = card.select_one(".btn_zak")

        if (
            link_element is None
            or price_element is None
            or buy_element is None
        ):
            return None

        anchor = link_element.find_parent("a", href=True)
        title = " ".join(
            str(link_element.get("alt", "")).split()
        )
        old_price = price_element.select_one("s")

        if old_price is not None:
            old_price.decompose()

        price = self._parse_decimal(
            price_element.get_text(" ", strip=True)
        )
        buy_text = buy_element.get_text(
            " ", strip=True
        ).casefold()

        if (
            anchor is None
            or not title
            or price is None
            or price <= 0
            or not any(
                marker in buy_text
                for marker in ("корзин", "купить")
            )
        ):
            return None

        product_url = self._product_url(
            str(anchor.get("href", ""))
        )

        if product_url is None:
            return None

        availability_element = card.select_one(
            ".action .act, .nal_box"
        )
        availability_text = "В наличии"

        if availability_element is not None:
            raw_availability = " ".join(
                availability_element.get_text(
                    " ", strip=True
                ).split()
            )

            if any(
                marker in raw_availability.casefold()
                for marker in ("остался", "в наличии")
            ):
                availability_text = raw_availability

        delivery_element = card.select_one(
            ".deliv_reys"
        )
        delivery_text = None

        if delivery_element is not None:
            raw_delivery = " ".join(
                delivery_element.get_text(
                    " ", strip=True
                ).split()
            )
            delivery_text = re.sub(
                r"^доставка\s*:\s*",
                "",
                raw_delivery,
                flags=re.IGNORECASE,
            ) or None

        return ProductOffer(
            source=self.source_name,
            title=title,
            price=float(price),
            currency="BYN",
            available=True,
            url=product_url,
            seller=self.source_name,
            availability_text=availability_text,
            delivery_text=delivery_text,
            updated_at=datetime.now().strftime(
                "%d.%m.%Y %H:%M"
            ),
        )

    def _product_url(self, raw_url: str) -> str | None:
        product_url = urljoin(self._base_url, raw_url)
        parsed = urlparse(product_url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in self._allowed_hosts
            or not parsed.path.startswith("/catalog/")
        ):
            return None

        return product_url

    def _next_page_url(
        self,
        soup: BeautifulSoup,
    ) -> str | None:
        link = soup.select_one("a.navi_dyn[href]")

        if link is None:
            return None

        raw_url = link.get("href")

        if not isinstance(raw_url, str):
            return None

        next_url = urljoin(self._base_url, raw_url)
        parsed = urlparse(next_url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in self._allowed_hosts
            or not parsed.path.startswith("/search/")
        ):
            return None

        return next_url

    @staticmethod
    def _decode_response(response: httpx.Response) -> str:
        return response.content.decode(
            "cp1251",
            errors="replace",
        )

    @staticmethod
    def _parse_decimal(value: object) -> Decimal | None:
        normalized = re.sub(
            r"[^0-9,.]",
            "",
            str(value),
        ).replace(",", ".")

        if not normalized:
            return None

        if normalized.count(".") > 1:
            integer, fraction = normalized.rsplit(".", 1)
            normalized = integer.replace(".", "") + "." + fraction

        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None
