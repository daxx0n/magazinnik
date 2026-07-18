from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.offer import ProductOffer
from app.sources import SourceUnavailableError


class ShopBySource:
    """Ищет предложения продавцов на Shop.by."""

    source_name = "Shop.by"

    _base_url = "https://shop.by"
    _search_url = f"{_base_url}/find/"

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
        """Возвращает предложения из результатов поиска."""

        normalized_query = " ".join(query.strip().split())

        if len(normalized_query) < 3 or limit <= 0:
            return []

        html = await self._download_search_page(
            normalized_query
        )

        return self._parse_search_results(
            html=html,
            limit=limit,
        )

    async def _download_search_page(
        self,
        query: str,
    ) -> str:
        """Загружает публичную страницу поиска Shop.by."""

        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    self._search_url,
                    params={"findtext": query},
                )

            response.raise_for_status()

        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "Поиск Shop.by не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            raise SourceUnavailableError(
                "Поиск Shop.by вернул HTTP-ошибку "
                f"{error.response.status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться к Shop.by."
            ) from error

        return response.text

    def _parse_search_results(
        self,
        html: str,
        limit: int,
    ) -> list[ProductOffer]:
        """Разбирает строки продавцов в выдаче Shop.by."""

        soup = BeautifulSoup(html, "html.parser")
        offers: dict[
            tuple[str, str],
            ProductOffer,
        ] = {}

        for row in soup.select(
            ".ShopItemList__ItemBlockRow"
        ):
            offer = self._parse_offer_row(row)

            if offer is None:
                continue

            unique_key = (
                (offer.seller or "").casefold(),
                offer.url,
            )
            previous = offers.get(unique_key)

            if previous is None or offer.price < previous.price:
                offers[unique_key] = offer

        return sorted(
            offers.values(),
            key=lambda offer: offer.price,
        )[:limit]

    def _parse_offer_row(
        self,
        row,
    ) -> ProductOffer | None:
        """Преобразует одну строку продавца."""

        title_element = row.select_one(
            ".ModelList__NameBlock"
        )
        price_element = row.select_one(
            '[itemprop="offers"] meta[itemprop="price"]'
        )
        seller_element = row.select_one(
            ".ShopItemList__ShopLink"
        )
        link_element = row.select_one(
            "a.ShopItemList__ItemName[href]"
        )

        if not all(
            element is not None
            for element in (
                title_element,
                price_element,
                seller_element,
                link_element,
            )
        ):
            return None

        title = title_element.get_text(
            separator=" ",
            strip=True,
        )
        seller = seller_element.get_text(
            separator=" ",
            strip=True,
        )
        price = self._parse_decimal(
            price_element.get("content")
        )
        raw_link = link_element.get("href")

        if (
            not title
            or not seller
            or price is None
            or price <= 0
            or not isinstance(raw_link, str)
        ):
            return None

        availability_element = row.select_one(
            '[itemprop="offers"] '
            'link[itemprop="availability"]'
        )
        availability_url = (
            availability_element.get("href", "")
            if availability_element is not None
            else ""
        )

        if str(availability_url).casefold().endswith(
            ("outofstock", "discontinued")
        ):
            return None

        delivery_element = row.select_one(
            'img[alt^="Доставка:"]'
        )
        delivery_text = None

        if delivery_element is not None:
            raw_delivery = delivery_element.get("alt")

            if isinstance(raw_delivery, str):
                delivery_text = raw_delivery.removeprefix(
                    "Доставка:"
                ).strip() or None

        return ProductOffer(
            source=self.source_name,
            title=title,
            price=float(price),
            currency="BYN",
            available=True,
            url=self._offer_url(raw_link),
            seller=seller,
            availability_text="В наличии",
            delivery_text=delivery_text,
            updated_at=datetime.now().strftime(
                "%d.%m.%Y %H:%M"
            ),
        )

    def _offer_url(self, raw_link: str) -> str:
        """Достаёт прямую ссылку продавца из редиректа."""

        redirect_url = urljoin(self._base_url, raw_link)
        target_urls = parse_qs(
            urlparse(redirect_url).query
        ).get("url", [])

        if target_urls:
            target_url = target_urls[0]
            parsed_target = urlparse(target_url)

            if (
                parsed_target.scheme in {"http", "https"}
                and parsed_target.hostname
            ):
                return target_url

        return redirect_url

    @staticmethod
    def _parse_decimal(
        value: object,
    ) -> Decimal | None:
        """Преобразует цену Shop.by в Decimal."""

        if value is None:
            return None

        normalized = (
            str(value)
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
        )

        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None
