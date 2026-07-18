import asyncio
import re
import time
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from urllib.parse import urlparse

import httpx

from app.models.category import ProductCategory
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.product_variants import extract_color
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

    _category_discovery_pages = 12
    _category_page_concurrency = 5
    _search_page_cache_ttl = 30.0
    _search_page_cache_size = 256
    _accessory_categories = {
        "cable",
        "chargersmobile",
        "phonecase",
        "protectiveglass",
        "screenprotector",
        "watchband",
    }
    _category_titles = {
        "activitytracker": "Фитнес-браслеты",
        "conditioner": "Кондиционеры",
        "dishwasher": "Посудомоечные машины",
        "ebook": "Электронные книги",
        "headphones": "Наушники",
        "hob_cooker": "Варочные панели",
        "keyboard": "Клавиатуры",
        "microwave": "Микроволновые печи",
        "mobile": "Телефоны и смартфоны",
        "monitor": "Мониторы",
        "mouse": "Мыши",
        "multifunctional": "МФУ",
        "notebook": "Ноутбуки",
        "oven_cooker": "Духовые шкафы",
        "portablecharger": "Внешние аккумуляторы",
        "printer": "Принтеры",
        "refrigerator": "Холодильники",
        "smartwatch": "Умные часы",
        "soundbar": "Саундбары",
        "tabletpc": "Планшеты",
        "tv": "Телевизоры",
        "vacuumcleaner": "Пылесосы",
        "washingmachine": "Стиральные машины",
    }

    def __init__(self) -> None:
        self._search_page_cache: OrderedDict[
            tuple[str, int],
            tuple[float, dict],
        ] = OrderedDict()
        self._search_page_tasks: dict[
            tuple[str, int],
            asyncio.Task[dict],
        ] = {}

    async def find_categories(
        self,
        query: str,
    ) -> list[ProductCategory]:
        """Находит товарные разделы для широкого запроса."""

        normalized_query = " ".join(query.strip().split())

        if len(normalized_query) < 3:
            return []

        categories: dict[str, ProductCategory] = {}
        query_brand_key = self._normalize_brand_key(
            normalized_query
        )

        def append_page(data: dict) -> bool:
            raw_products = data.get("products", [])

            if not isinstance(raw_products, list) or not raw_products:
                return False

            for raw_product in raw_products:
                if not isinstance(raw_product, dict):
                    continue

                candidate = self._parse_candidate(raw_product)

                if candidate is None:
                    continue

                if self._product_brand_key(candidate.url) != (
                    query_brand_key
                ):
                    continue

                category_key = self._product_category_key(
                    raw_product,
                    candidate,
                )

                if (
                    not category_key
                    or category_key in self._accessory_categories
                ):
                    continue

                categories.setdefault(
                    category_key,
                    ProductCategory(
                        key=category_key,
                        title=self._category_title(category_key),
                    ),
                )

            return True

        async with self._create_client() as client:
            async def load_page(page: int) -> dict:
                return await self._load_search_page(
                    client=client,
                    query=normalized_query,
                    page=page,
                )

            first_page = await load_page(1)

            if not append_page(first_page):
                return []

            last_page = min(
                self._last_page(
                    data=first_page,
                    fallback=1,
                ),
                self._category_discovery_pages,
            )
            next_page = 2

            while next_page <= last_page:
                batch_end = min(
                    next_page + self._category_page_concurrency,
                    last_page + 1,
                )
                pages = await asyncio.gather(
                    *(
                        load_page(page)
                        for page in range(next_page, batch_end)
                    )
                )

                for data in pages:
                    append_page(data)

                next_page = batch_end

        return list(categories.values())

    async def find_products(
        self,
        query: str,
        limit: int | None = None,
        category: str | None = None,
    ) -> list[ProductCandidate]:
        """Ищет карточки Onliner по названию товара."""

        normalized_query = " ".join(
            query.strip().split()
        )

        if len(normalized_query) < 3:
            return []

        if category is not None:
            return await self._find_products_in_category(
                query=normalized_query,
                category=category,
                limit=limit,
            )

        candidates: list[ProductCandidate] = []
        used_keys: set[str] = set()
        primary_category = category
        pages_without_primary_products = 0
        primary_category_seen = False
        page = 1
        last_page = 100

        async with self._create_client() as client:
            while page <= 100:
                data = await self._load_search_page(
                    client=client,
                    query=normalized_query,
                    page=page,
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

                last_page = self._last_page(
                    data=data,
                    fallback=page,
                )

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
                        self._product_category_key(
                            raw_product,
                            candidate,
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
                    primary_category_seen = True

                    if (
                        limit is not None
                        and len(candidates) >= limit
                    ):
                        return self._group_variants(
                            candidates
                        )

                if added_on_page == 0 and primary_category_seen:
                    pages_without_primary_products += 1
                else:
                    pages_without_primary_products = 0

                # В обычном поиске после основных товаров обычно
                # идут аксессуары, поэтому две пустые страницы
                # завершают обход. При явно выбранной категории
                # результаты могут быть разбросаны по всей выдаче:
                # её нужно дочитать до последней страницы.
                if (
                    category is None
                    and pages_without_primary_products >= 2
                ):
                    break

                page += 1

                if page > last_page:
                    break

        grouped_candidates = self._group_variants(
            candidates
        )

        return self._sort_product_family(
            candidates=grouped_candidates,
            query=normalized_query,
        )

    async def _find_products_in_category(
        self,
        query: str,
        category: str,
        limit: int | None,
    ) -> list[ProductCandidate]:
        """Параллельно дочитывает выдачу выбранной категории."""

        candidates: list[ProductCandidate] = []
        used_keys: set[str] = set()

        def append_page(data: dict) -> None:
            raw_products = data.get("products", [])

            if not isinstance(raw_products, list):
                return

            for raw_product in raw_products:
                if not isinstance(raw_product, dict):
                    continue

                candidate = self._parse_candidate(raw_product)

                if (
                    candidate is None
                    or candidate.key in used_keys
                    or self._product_category_key(
                        raw_product,
                        candidate,
                    )
                    != category
                ):
                    continue

                used_keys.add(candidate.key)
                candidates.append(candidate)

        async with self._create_client() as client:
            async def load_page(page: int) -> dict:
                return await self._load_search_page(
                    client=client,
                    query=query,
                    page=page,
                )

            first_page = await load_page(1)
            append_page(first_page)

            if limit is not None and len(candidates) >= limit:
                grouped = self._group_variants(candidates[:limit])
                return self._sort_product_family(
                    candidates=grouped,
                    query=query,
                )

            last_page = self._last_page(
                data=first_page,
                fallback=1,
            )

            next_page = 2

            while next_page <= last_page:
                batch_end = min(
                    next_page + self._category_page_concurrency,
                    last_page + 1,
                )
                pages = await asyncio.gather(
                    *(
                        load_page(page)
                        for page in range(next_page, batch_end)
                    )
                )

                for data in pages:
                    append_page(data)

                    if limit is not None and len(candidates) >= limit:
                        grouped = self._group_variants(
                            candidates[:limit]
                        )
                        return self._sort_product_family(
                            candidates=grouped,
                            query=query,
                        )

                next_page = batch_end

        grouped_candidates = self._group_variants(candidates)
        return self._sort_product_family(
            candidates=grouped_candidates,
            query=query,
        )

    async def _load_search_page(
        self,
        client,
        query: str,
        page: int,
    ) -> dict:
        """Кэширует страницу поиска и объединяет одинаковые запросы."""

        cache_key = (
            " ".join(query.casefold().split()),
            page,
        )
        cached = self._search_page_cache.get(cache_key)
        now = time.monotonic()

        if cached is not None:
            cached_at, data = cached

            if now - cached_at <= self._search_page_cache_ttl:
                self._search_page_cache.move_to_end(cache_key)
                return data

            self._search_page_cache.pop(cache_key, None)

        task = self._search_page_tasks.get(cache_key)

        if task is None:
            task = asyncio.create_task(
                self._request_json(
                    client=client,
                    url=self._search_endpoint,
                    params={
                        "query": query,
                        "page": str(page),
                    },
                )
            )
            self._search_page_tasks[cache_key] = task
            task.add_done_callback(
                partial(
                    self._complete_search_page,
                    cache_key,
                )
            )

        return await asyncio.shield(task)

    def _complete_search_page(
        self,
        cache_key: tuple[str, int],
        task: asyncio.Task[dict],
    ) -> None:
        """Сохраняет только успешно загруженную страницу."""

        if self._search_page_tasks.get(cache_key) is task:
            self._search_page_tasks.pop(cache_key, None)

        if task.cancelled() or task.exception() is not None:
            return

        self._search_page_cache[cache_key] = (
            time.monotonic(),
            task.result(),
        )
        self._search_page_cache.move_to_end(cache_key)

        while len(self._search_page_cache) > self._search_page_cache_size:
            self._search_page_cache.popitem(last=False)

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
    def _product_brand_key(product_url: str) -> str:
        """Получает производителя из URL карточки."""

        path_parts = [
            part
            for part in urlparse(product_url).path.split("/")
            if part
        ]

        if len(path_parts) < 2:
            return ""

        return OnlinerSource._normalize_brand_key(path_parts[1])

    @staticmethod
    def _normalize_brand_key(value: str) -> str:
        """Нормализует бренд для сравнения с URL каталога."""

        return re.sub(
            r"[^a-zа-яё0-9]+",
            "",
            value.casefold(),
        )

    @classmethod
    def _product_category_key(
        cls,
        raw_product: dict,
        candidate: ProductCandidate,
    ) -> str:
        """Берёт ключ раздела из API с резервом по URL."""

        raw_schema = raw_product.get("schema")

        if isinstance(raw_schema, dict):
            schema_key = raw_schema.get("key")

            if isinstance(schema_key, str) and schema_key:
                return schema_key

        return cls._extract_category(candidate.url)

    @classmethod
    def _category_title(cls, category_key: str) -> str:
        """Возвращает понятное название раздела."""

        known_title = cls._category_titles.get(category_key)

        if known_title is not None:
            return known_title

        return category_key.replace("_", " ").capitalize()

    @staticmethod
    def _last_page(data: dict, fallback: int) -> int:
        """Читает число страниц из ответа поиска."""

        raw_page = data.get("page")

        if not isinstance(raw_page, dict):
            return fallback + 1

        raw_last = raw_page.get("last")

        if not isinstance(raw_last, int) or raw_last < 1:
            return fallback

        return min(raw_last, 100)

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

        if extract_color(title) is None:
            return title

        return re.sub(
            r"\s*\([^()]*\)\s*$",
            "",
            title,
        )

    @staticmethod
    def _sort_product_family(
        candidates: list[ProductCandidate],
        query: str,
    ) -> list[ProductCandidate]:
        """Сортирует поколения и версии известных семейств."""

        iphone_candidates = [
            candidate
            for candidate in candidates
            if re.search(
                r"\biphone\b",
                candidate.title,
                re.IGNORECASE,
            )
        ]

        if (
            "iphone" not in query.casefold()
            and len(iphone_candidates) != len(candidates)
        ):
            return candidates

        generations = [
            int(match.group(1))
            for candidate in candidates
            if (
                match := re.search(
                    r"\biphone\s+(\d{1,2})(?:e)?\b",
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
                r"\biphone\s+(\d{1,2})(?:e)?\b",
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
                version_rank = 3
            elif re.search(r"\bpro\b", title):
                version_rank = 2
            elif re.search(r"\biphone\s+\d{1,2}e\b", title):
                version_rank = 1
            elif re.search(r"\bplus\b", title):
                version_rank = 4
            elif re.search(r"\bair\b", title):
                version_rank = 5
            else:
                version_rank = 0

            if re.search(r"\bdual\s+e\s*sim\b", title):
                sim_rank = 2
            elif re.search(r"\bdual\s*sim\b", title):
                sim_rank = 1
            elif re.search(r"\be\s*sim\b", title):
                sim_rank = 3
            else:
                sim_rank = 0

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
