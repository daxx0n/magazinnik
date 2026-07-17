import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.sources import (
    InvalidProductUrlError,
    ProductNotFoundError,
    SourceUnavailableError,
)


class OnlinerSource:
    """Поиск товаров и предложений продавцов Onliner."""

    source_name = "Onliner"

    _catalog_host = "catalog.onliner.by"

    _search_endpoint = (
        "https://www.onliner.by/"
        "sdapi/catalog.api/search/products"
    )

    _product_endpoint = (
        "https://catalog.api.onliner.by/products"
    )

    _headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "application/json",
    }

    _timeout = httpx.Timeout(
        connect=10.0,
        read=20.0,
        write=10.0,
        pool=10.0,
    )

    async def find_products(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[ProductCandidate]:
        """Ищет карточки Onliner по названию товара."""

        normalized_query = " ".join(
            query.strip().split()
        )

        if len(normalized_query) < 3:
            return []

        candidates: list[ProductCandidate] = []
        used_keys: set[str] = set()
        primary_category: str | None = None
        pages_without_primary_products = 0
        page = 1

        async with self._create_client() as client:
            while page <= 100:
                data = await self._request_json(
                    client=client,
                    url=self._search_endpoint,
                    params={
                        "query": normalized_query,
                        "page": str(page),
                    },
                )
                raw_products = data.get(
                    "products",
                    [],
                )

                if (
                    not isinstance(raw_products, list)
                    or not raw_products
                ):
                    break

                added_on_page = 0

                for raw_product in raw_products:
                    if not isinstance(raw_product, dict):
                        continue

                    candidate = self._parse_candidate(
                        raw_product
                    )

                    if (
                        candidate is None
                        or candidate.key in used_keys
                    ):
                        continue

                    candidate_category = (
                        self._extract_category(
                            candidate.url
                        )
                    )

                    if primary_category is None:
                        primary_category = candidate_category

                    if (
                        candidate_category
                        != primary_category
                    ):
                        continue

                    used_keys.add(candidate.key)
                    candidates.append(candidate)
                    added_on_page += 1

                    if (
                        limit is not None
                        and len(candidates) >= limit
                    ):
                        return self._group_variants(
                            candidates
                        )

                if added_on_page == 0:
                    pages_without_primary_products += 1
                else:
                    pages_without_primary_products = 0

                # Поиск Onliner после основных товаров может
                # продолжаться аксессуарами других категорий.
                # Две страницы без основной категории означают,
                # что релевантная часть выдачи закончилась.
                if pages_without_primary_products >= 2:
                    break

                page += 1

        grouped_candidates = self._group_variants(
            candidates
        )

        return self._sort_product_family(
            candidates=grouped_candidates,
            query=normalized_query,
        )

    @staticmethod
    def _extract_category(product_url: str) -> str:
        """Получает раздел каталога из URL товара."""

        path_parts = [
            part
            for part in urlparse(product_url).path.split("/")
            if part
        ]

        return path_parts[0] if path_parts else ""

    @staticmethod
    def _group_variants(
        candidates: list[ProductCandidate],
    ) -> list[ProductCandidate]:
        """Ставит цвета одной модификации рядом."""

        groups: dict[str, list[ProductCandidate]] = {}

        for candidate in candidates:
            base_title = (
                OnlinerSource._base_variant_title(
                    candidate.title
                )
            )
            group_key = " ".join(
                base_title.casefold().split()
            )
            groups.setdefault(group_key, []).append(
                candidate
            )

        return [
            candidate
            for group in groups.values()
            for candidate in group
        ]

    @staticmethod
    def _base_variant_title(title: str) -> str:
        """Убирает цвет из конца названия варианта."""

        return re.sub(
            r"\s*\([^()]*(?:цвет|черн|бел|син|"
            r"голуб|зелен|желт|красн|фиолет|"
            r"сирен|лилов|розов|оранж|графит|"
            r"серебр|золот|титан)[^()]*\)\s*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _sort_product_family(
        candidates: list[ProductCandidate],
        query: str,
    ) -> list[ProductCandidate]:
        """Сортирует поколения и версии известных семейств."""

        if "iphone" not in query.casefold():
            return candidates

        generations = [
            int(match.group(1))
            for candidate in candidates
            if (
                match := re.search(
                    r"\biphone\s+(\d{1,2})\b",
                    candidate.title.casefold(),
                )
            )
        ]
        latest_generation = max(
            generations,
            default=-1,
        )

        def iphone_sort_key(
            candidate: ProductCandidate,
        ) -> tuple[int, int, int, str]:
            title = candidate.title.casefold()
            generation_match = re.search(
                r"\biphone\s+(\d{1,2})\b",
                title,
            )
            generation = (
                int(generation_match.group(1))
                if generation_match
                else (
                    latest_generation
                    if re.search(
                        r"\biphone\s+air\b",
                        title,
                    )
                    else -1
                )
            )

            if "pro max" in title:
                version_rank = 2
            elif re.search(r"\bpro\b", title):
                version_rank = 1
            elif re.search(r"\bplus\b", title):
                version_rank = 3
            elif re.search(r"\bair\b", title):
                version_rank = 4
            else:
                version_rank = 0

            sim_rank = (
                1
                if re.search(
                    r"\bdual\s*sim\b",
                    title,
                )
                else 0
            )

            return (
                -generation,
                version_rank,
                sim_rank,
                OnlinerSource._base_variant_title(
                    title
                ),
            )

        return sorted(
            candidates,
            key=iphone_sort_key,
        )

    async def search(
        self,
        query: str,
    ) -> list[ProductOffer]:
        """Получает предложения по прямой ссылке Onliner."""

        product_url = self._validate_url(query)
        product_key = self._extract_product_key(
            product_url
        )

        return await self.search_by_key(
            product_key
        )

    async def search_by_key(
        self,
        product_key: str,
    ) -> list[ProductOffer]:
        """Получает предложения по ключу товара Onliner."""

        self._validate_product_key(product_key)

        product_endpoint = (
            f"{self._product_endpoint}/{product_key}"
        )

        positions_endpoint = (
            "https://catalog.onliner.by/"
            f"sdapi/shop.api/products/"
            f"{product_key}/positions"
        )

        async with self._create_client() as client:
            product_data = await self._request_json(
                client=client,
                url=product_endpoint,
            )

            product_title = self._get_product_title(
                product_data
            )

            product_url = self._get_product_url(
                product_data
            )

            positions_data = await self._request_json(
                client=client,
                url=positions_endpoint,
                headers={
                    "Referer": product_url,
                },
            )

        offers = self._parse_positions(
            data=positions_data,
            product_title=product_title,
            product_url=product_url,
        )

        if not offers:
            raise ProductNotFoundError(
                "Onliner не вернул предложений продавцов."
            )

        return sorted(
            offers,
            key=lambda offer: offer.price,
        )

    def _create_client(
        self,
    ) -> httpx.AsyncClient:
        """Создаёт HTTP-клиент."""

        return httpx.AsyncClient(
            headers=self._headers,
            timeout=self._timeout,
            follow_redirects=True,
        )

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        """Выполняет запрос и проверяет JSON-ответ."""

        try:
            response = await client.get(
                url,
                params=params,
                headers=headers,
            )

            response.raise_for_status()

        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "Onliner не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            status_code = (
                error.response.status_code
            )

            if status_code == 404:
                raise ProductNotFoundError(
                    "Товар Onliner не найден."
                ) from error

            raise SourceUnavailableError(
                "Onliner вернул HTTP-ошибку "
                f"{status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось подключиться к Onliner."
            ) from error

        try:
            data = response.json()
        except ValueError as error:
            raise SourceUnavailableError(
                "Onliner вернул ответ "
                "в неожиданном формате."
            ) from error

        if not isinstance(data, dict):
            raise SourceUnavailableError(
                "Onliner вернул некорректный JSON."
            )

        return data

    def _validate_url(
        self,
        value: str,
    ) -> str:
        """Проверяет прямую ссылку Onliner."""

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

        if parsed_url.hostname != self._catalog_host:
            raise InvalidProductUrlError(
                "Поддерживаются только ссылки "
                "catalog.onliner.by."
            )

        path_parts = [
            part
            for part in parsed_url.path.split("/")
            if part
        ]

        if len(path_parts) < 3:
            raise InvalidProductUrlError(
                "Ссылка не похожа "
                "на карточку товара Onliner."
            )

        base_parts = path_parts[:3]

        return (
            f"https://{self._catalog_host}/"
            + "/".join(base_parts)
        )

    @staticmethod
    def _validate_product_key(
        product_key: str,
    ) -> None:
        """Проверяет ключ, полученный из callback."""

        if not product_key:
            raise ProductNotFoundError(
                "Не передан ключ товара."
            )

        if len(product_key) > 50:
            raise ProductNotFoundError(
                "Некорректный ключ товара."
            )

        allowed_characters = set(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789_-"
        )

        if any(
            character not in allowed_characters
            for character in product_key
        ):
            raise ProductNotFoundError(
                "Некорректный ключ товара."
            )

    @staticmethod
    def _extract_product_key(
        product_url: str,
    ) -> str:
        """Получает ключ из URL карточки."""

        parsed_url = urlparse(product_url)

        path_parts = [
            part
            for part in parsed_url.path.split("/")
            if part
        ]

        return path_parts[-1]

    def _parse_candidate(
        self,
        product: dict,
    ) -> ProductCandidate | None:
        """Преобразует результат поиска."""

        title = (
            product.get("full_name")
            or product.get("name")
        )

        product_url = product.get("html_url")
        product_key = product.get("key")

        if not isinstance(title, str):
            return None

        if not isinstance(product_url, str):
            return None

        if not product_key:
            product_key = self._extract_key_from_url(
                product_url
            )

        if not isinstance(product_key, str):
            return None

        if len(product_key) > 50:
            return None

        product_url = product_url.replace(
            "http://",
            "https://",
            1,
        )

        parsed_url = urlparse(product_url)

        if parsed_url.hostname != self._catalog_host:
            return None

        return ProductCandidate(
            key=product_key,
            title=title.strip(),
            url=product_url,
        )

    @staticmethod
    def _extract_key_from_url(
        product_url: str,
    ) -> str | None:
        """Получает ключ из URL результата поиска."""

        parsed_url = urlparse(product_url)

        path_parts = [
            part
            for part in parsed_url.path.split("/")
            if part
        ]

        if len(path_parts) < 3:
            return None

        return path_parts[-1]

    @staticmethod
    def _get_product_title(
        product_data: dict,
    ) -> str:
        """Получает полное название товара."""

        title = (
            product_data.get("full_name")
            or product_data.get("name")
        )

        if not isinstance(title, str):
            raise ProductNotFoundError(
                "Не удалось определить название товара."
            )

        return title.strip()

    @staticmethod
    def _get_product_url(
        product_data: dict,
    ) -> str:
        """Получает URL карточки товара."""

        product_url = product_data.get("html_url")

        if not isinstance(product_url, str):
            raise ProductNotFoundError(
                "Не удалось определить ссылку товара."
            )

        return product_url.replace(
            "http://",
            "https://",
            1,
        )

    def _parse_positions(
        self,
        data: dict,
        product_title: str,
        product_url: str,
    ) -> list[ProductOffer]:
        """Преобразует позиции продавцов."""

        positions_container = data.get(
            "positions",
            {},
        )

        if not isinstance(
            positions_container,
            dict,
        ):
            return []

        positions = positions_container.get(
            "primary",
            [],
        )

        shops = data.get("shops", {})

        if not isinstance(positions, list):
            return []

        if not isinstance(shops, dict):
            shops = {}

        offers: list[ProductOffer] = []

        for position in positions:
            if not isinstance(position, dict):
                continue

            price = self._extract_price(position)

            if price is None:
                continue

            shop_id = position.get("shop_id")
            shop = shops.get(str(shop_id), {})

            if not isinstance(shop, dict):
                shop = {}

            seller = shop.get("title")

            if not isinstance(seller, str):
                seller = f"Магазин #{shop_id}"

            seller_url = shop.get("html_url")

            if not isinstance(seller_url, str):
                seller_url = (
                    product_url.rstrip("/")
                    + "/prices"
                )

            seller_url = seller_url.replace(
                "http://",
                "https://",
                1,
            )

            availability_text = (
                self._get_availability_text(
                    position
                )
            )

            available = (
                availability_text != "Предзаказ"
            )

            offers.append(
                ProductOffer(
                    source=self.source_name,
                    title=product_title,
                    price=float(price),
                    currency="BYN",
                    available=available,
                    url=seller_url,
                    seller=seller,
                    availability_text=(
                        availability_text
                    ),
                    delivery_text=(
                        self._get_delivery_text(
                            position
                        )
                    ),
                    updated_at=(
                        self._format_update_time(
                            position.get(
                                "date_update"
                            )
                        )
                    ),
                )
            )

        return offers

    @staticmethod
    def _extract_price(
        position: dict,
    ) -> Decimal | None:
        """Получает полную цену товара."""

        position_price = position.get(
            "position_price"
        )

        if not isinstance(
            position_price,
            dict,
        ):
            return None

        amount = position_price.get("amount")

        if amount is None:
            return None

        try:
            return Decimal(str(amount))
        except InvalidOperation:
            return None

    @staticmethod
    def _get_availability_text(
        position: dict,
    ) -> str:
        """Определяет наличие."""

        shipping = position.get("shipping")

        if isinstance(shipping, dict):
            if shipping.get("preorder") is True:
                return "Предзаказ"

        prime_info = position.get("prime_info")

        if isinstance(prime_info, dict):
            quantity = prime_info.get(
                "quantity_left"
            )

            if (
                isinstance(quantity, int)
                and quantity > 0
            ):
                return (
                    f"В наличии: {quantity} шт."
                )

        stock_status = position.get(
            "stock_status"
        )

        if isinstance(stock_status, dict):
            stock_code = stock_status.get(
                "code"
            )

            if stock_code == "in_stock":
                return "В наличии"

            if stock_code == "run_out_of_stock":
                return "Ограниченное количество"

        if isinstance(shipping, dict):
            if shipping.get("term"):
                return "Доступен к заказу"

        delivery = position.get("delivery")

        if isinstance(delivery, dict):
            pickup_point = delivery.get(
                "pickup_point"
            )

            if isinstance(
                pickup_point,
                dict,
            ):
                items = pickup_point.get("items")

                if (
                    isinstance(items, list)
                    and items
                ):
                    return (
                        "Доступен для самовывоза"
                    )

        return "Наличие уточнить"

    @staticmethod
    def _get_delivery_text(
        position: dict,
    ) -> str | None:
        """Получает срок доставки."""

        shipping = position.get("shipping")

        if isinstance(shipping, dict):
            term = shipping.get("term")

            if term:
                return str(term)

        return None

    @staticmethod
    def _format_update_time(
        value: object,
    ) -> str | None:
        """Форматирует время обновления."""

        if not isinstance(value, str):
            return None

        try:
            parsed_value = datetime.fromisoformat(
                value
            )
        except ValueError:
            return value

        return parsed_value.strftime(
            "%d.%m.%Y %H:%M"
        )
