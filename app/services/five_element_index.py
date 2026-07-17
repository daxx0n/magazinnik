import asyncio
import gzip
import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from app.models.product import ProductCandidate
from app.sources import (
    ProductNotFoundError,
    SourceUnavailableError,
)


logger = logging.getLogger(__name__)


class FiveElementIndex:
    """Локальный поисковый индекс товаров 5element.by."""

    _sitemap_url = (
        "https://5element.by/sitemap/sitemap_index.xml"
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
    }

    _timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

    def __init__(
        self,
        index_path: Path | None = None,
    ) -> None:
        self._index_path = index_path or Path(
            "data/five_element_index.json"
        )

    async def rebuild(self) -> int:
        """
        Загружает sitemap и сохраняет
        список карточек товаров локально.
        """

        sitemap_queue = [self._sitemap_url]
        visited_sitemaps: set[str] = set()
        product_urls: set[str] = set()

        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=self._timeout,
            follow_redirects=True,
        ) as client:
            while sitemap_queue:
                sitemap_url = sitemap_queue.pop()

                if sitemap_url in visited_sitemaps:
                    continue

                visited_sitemaps.add(sitemap_url)

                try:
                    xml_content = await self._download_xml(
                        client=client,
                        url=sitemap_url,
                    )
                except SourceUnavailableError:
                    if sitemap_url == self._sitemap_url:
                        raise

                    logger.warning(
                        "Не удалось обработать sitemap: %s",
                        sitemap_url,
                    )
                    continue

                child_sitemaps, urls = (
                    self._parse_sitemap(
                        xml_content
                    )
                )

                sitemap_queue.extend(
                    child_url
                    for child_url in child_sitemaps
                    if child_url
                    not in visited_sitemaps
                )

                for url in urls:
                    if self._is_product_url(url):
                        product_urls.add(
                            self._clean_product_url(
                                url
                            )
                        )

        candidates = [
            self._candidate_from_url(url)
            for url in sorted(product_urls)
        ]

        candidates = [
            candidate
            for candidate in candidates
            if candidate is not None
        ]

        if not candidates:
            raise SourceUnavailableError(
                "В sitemap 5 элемента "
                "не найдены товары."
            )

        payload = {
            "generated_at": (
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ),
            "products": [
                asdict(candidate)
                for candidate in candidates
            ],
        }

        await asyncio.to_thread(
            self._write_index,
            payload,
        )

        return len(candidates)

    def find_products(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        """Ищет подходящие товары в локальном индексе."""

        products = self._load_products()
        normalized_query = self._normalize(query)

        if len(normalized_query) < 3:
            return []

        query_tokens = set(
            normalized_query.split()
        )

        memory_pattern = (
            r"\b(\d+)\s*"
            r"(gb|tb|mb|гб|тб|мб)\b"
        )

        # Например:
        # 256GB -> {("256", "gb")}
        query_memory_specs = {
            (
                amount,
                self._normalize_memory_unit(unit),
            )
            for amount, unit in re.findall(
                memory_pattern,
                normalized_query,
            )
        }

        # Числа, относящиеся к памяти.
        memory_amounts = {
            amount
            for amount, _ in query_memory_specs
        }

        # Числа модели без объёма памяти.
        # iPhone 17 256GB -> {"17"}
        query_model_numbers = (
            set(
                re.findall(
                    r"\d+",
                    normalized_query,
                )
            )
            - memory_amounts
        )

        ignored_units = {
            "gb",
            "tb",
            "mb",
            "гб",
            "тб",
            "мб",
        }

        query_words = {
            token
            for token in query_tokens
            if (
                token.isalpha()
                and token not in ignored_units
            )
        }

        accessory_markers = {
            "chehol",
            "чехол",
            "chekhol",
            "bamper",
            "case",
            "cover",
            "nakladka",
            "накладка",
            "steklo",
            "стекло",
            "plenka",
            "пленка",
            "zaschit",
            "защит",
            "kabel",
            "кабель",
            "adapter",
            "адаптер",
            "zaryad",
            "заряд",
            "derzhatel",
            "держатель",
            "remeshok",
            "ремешок",
            "ringke",
            "onyx",
            "fusion",
            "magnetic",
            "magnit",
            "магнит",
        }

        query_is_accessory = any(
            marker in normalized_query
            for marker in accessory_markers
        )

        ranked: list[
            tuple[float, ProductCandidate]
        ] = []

        for product in products:
            search_value = (
                f"{product.title} {product.url}"
            )

            normalized_product = self._normalize(
                search_value
            )

            product_tokens = set(
                normalized_product.split()
            )

            product_is_accessory = any(
                marker in normalized_product
                for marker in accessory_markers
            )

            # Исключаем аксессуары,
            # когда пользователь ищет устройство.
            if (
                product_is_accessory
                and not query_is_accessory
            ):
                continue

            product_memory_specs = {
                (
                    amount,
                    self._normalize_memory_unit(
                        unit
                    ),
                )
                for amount, unit in re.findall(
                    memory_pattern,
                    normalized_product,
                )
            }

            # Память должна совпадать:
            # 256GB в запросе и 256GB в товаре.
            if (
                query_memory_specs
                and not query_memory_specs.issubset(
                    product_memory_specs
                )
            ):
                continue

            product_numbers = set(
                re.findall(
                    r"\d+",
                    normalized_product,
                )
            )

            # Номер модели должен совпадать:
            # например iPhone 17.
            if not query_model_numbers.issubset(
                product_numbers
            ):
                continue

            matching_words = {
                word
                for word in query_words
                if (
                    word in product_tokens
                    or word in normalized_product
                )
            }

            # Должно совпасть основное слово:
            # iphone, samsung, xiaomi и т. д.
            if (
                query_words
                and not matching_words
            ):
                continue

            word_score = (
                len(matching_words)
                / max(len(query_words), 1)
            )

            number_score = (
                len(
                    query_model_numbers
                    & product_numbers
                )
                / max(
                    len(query_model_numbers),
                    1,
                )
                if query_model_numbers
                else 1.0
            )

            similarity = SequenceMatcher(
                None,
                normalized_query,
                normalized_product,
            ).ratio()

            device_bonus = 0.0

            device_markers = {
                "telefon",
                "телефон",
                "smartfon",
                "смартфон",
                "gsm",
            }

            if any(
                marker in normalized_product
                for marker in device_markers
            ):
                device_bonus = 0.3

            score = (
                word_score * 0.45
                + number_score * 0.30
                + similarity * 0.25
                + device_bonus
            )

            ranked.append(
                (score, product)
            )

        ranked.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            product
            for _, product in ranked[:limit]
        ]

    def get_by_key(
        self,
        product_key: str,
    ) -> ProductCandidate:
        """Находит товар по ключу Telegram-кнопки."""

        for product in self._load_products():
            if product.key == product_key:
                return product

        raise ProductNotFoundError(
            "Карточка 5 элемента отсутствует "
            "в локальном индексе."
        )

    async def _download_xml(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> bytes:
        """Загружает sitemap XML."""

        try:
            response = await client.get(url)
            response.raise_for_status()

        except httpx.TimeoutException as error:
            raise SourceUnavailableError(
                "Sitemap 5 элемента "
                "не ответил вовремя."
            ) from error

        except httpx.HTTPStatusError as error:
            raise SourceUnavailableError(
                "Sitemap 5 элемента вернул "
                f"HTTP {error.response.status_code}."
            ) from error

        except httpx.RequestError as error:
            raise SourceUnavailableError(
                "Не удалось загрузить "
                "sitemap 5 элемента."
            ) from error

        content = response.content

        if content.startswith(b"\x1f\x8b"):
            try:
                return gzip.decompress(content)
            except OSError as error:
                raise SourceUnavailableError(
                    "Не удалось распаковать "
                    "sitemap 5 элемента."
                ) from error

        return content

    @staticmethod
    def _parse_sitemap(
        xml_content: bytes,
    ) -> tuple[list[str], list[str]]:
        """
        Читает sitemapindex или urlset
        независимо от XML namespace.
        """

        try:
            root = ET.fromstring(
                xml_content
            )
        except ET.ParseError as error:
            raise SourceUnavailableError(
                "5 элемент вернул "
                "некорректный sitemap XML."
            ) from error

        root_name = root.tag.rsplit(
            "}",
            1,
        )[-1]

        locations = [
            element.text.strip()
            for element in root.iter()
            if (
                element.tag.rsplit(
                    "}",
                    1,
                )[-1]
                == "loc"
                and element.text
            )
        ]

        if root_name == "sitemapindex":
            return locations, []

        if root_name == "urlset":
            return [], locations

        return [], []

    @staticmethod
    def _is_product_url(
        url: str,
    ) -> bool:
        """
        Пропускает только основные карточки товаров.

        Подходящий URL:
        /products/iphone-17-256gb-black-...

        Неподходящие URL:
        /products/iphone-17-256gb-black-.../reviews
        /products/iphone-17-256gb-black-.../characteristics
        """

        parsed_url = urlparse(url)

        if parsed_url.hostname not in {
            "5element.by",
            "www.5element.by",
        }:
            return False

        path_parts = [
            part
            for part in parsed_url.path.split("/")
            if part
        ]

        return (
            len(path_parts) == 2
            and path_parts[0] == "products"
            and bool(path_parts[1])
        )

    @staticmethod
    def _clean_product_url(
        url: str,
    ) -> str:
        """Удаляет параметры и приводит домен к одному виду."""

        parsed_url = urlparse(url)

        clean_path = (
            parsed_url.path.rstrip("/")
        )

        return (
            f"https://5element.by{clean_path}"
        )

    def _candidate_from_url(
        self,
        url: str,
    ) -> ProductCandidate | None:
        """Создаёт карточку товара из URL sitemap."""

        parsed_url = urlparse(url)

        path_parts = [
            part
            for part in parsed_url.path.split("/")
            if part
        ]

        if (
            len(path_parts) != 2
            or path_parts[0] != "products"
        ):
            return None

        slug = path_parts[1]

        if not slug:
            return None

        title = self._title_from_slug(slug)

        if not title:
            return None

        key = hashlib.sha1(
            url.encode("utf-8")
        ).hexdigest()[:12]

        return ProductCandidate(
            key=key,
            title=title,
            url=url,
        )

    @staticmethod
    def _title_from_slug(
        slug: str,
    ) -> str:
        """Преобразует URL-slug в читаемый текст."""

        text = (
            unquote(slug)
            .replace("-", " ")
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        replacements = {
            "iphone": "iPhone",
            "apple": "Apple",
            "samsung": "Samsung",
            "xiaomi": "Xiaomi",
            "gb": "GB",
            "tb": "TB",
            "gsm": "GSM",
        }

        words = [
            replacements.get(
                word.casefold(),
                word,
            )
            for word in text.split()
        ]

        return " ".join(words)

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        """
        Нормализует строку для поиска.

        Приводит варианты:
        256GB
        256 GB
        256-GB

        к единому виду:
        256gb
        """

        value = unquote(value).casefold()

        value = value.replace(
            "ё",
            "е",
        )

        # Заменяем дефисы и специальные символы
        # обычными пробелами.
        value = re.sub(
            r"[^a-zа-я0-9]+",
            " ",
            value,
        )

        # Разделяем буквы и цифры:
        # iphone17 -> iphone 17
        # s25 -> s 25
        # 256gb -> 256 gb
        value = re.sub(
            r"([a-zа-я])(\d)",
            r"\1 \2",
            value,
        )

        value = re.sub(
            r"(\d)([a-zа-я])",
            r"\1 \2",
            value,
        )

        # Снова объединяем объём памяти:
        # 256 gb -> 256gb
        # 1 tb -> 1tb
        # 256 гб -> 256гб
        value = re.sub(
            r"\b(\d+)\s+"
            r"(gb|tb|mb|гб|тб|мб)\b",
            r"\1\2",
            value,
        )

        return " ".join(
            value.split()
        )

    @staticmethod
    def _normalize_memory_unit(
        unit: str,
    ) -> str:
        """Приводит единицы памяти к единому виду."""

        normalized_unit = unit.casefold()

        units_map = {
            "gb": "gb",
            "гб": "gb",
            "tb": "tb",
            "тб": "tb",
            "mb": "mb",
            "мб": "mb",
        }

        return units_map.get(
            normalized_unit,
            normalized_unit,
        )

    def _load_products(
        self,
    ) -> list[ProductCandidate]:
        """Загружает локальный индекс."""

        if not self._index_path.exists():
            raise SourceUnavailableError(
                "Индекс 5 элемента ещё не создан. "
                "Запусти scripts/build_five_index.py."
            )

        try:
            payload = json.loads(
                self._index_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise SourceUnavailableError(
                "Не удалось прочитать "
                "индекс 5 элемента."
            ) from error

        raw_products = payload.get(
            "products",
            [],
        )

        if not isinstance(
            raw_products,
            list,
        ):
            raise SourceUnavailableError(
                "Индекс 5 элемента повреждён."
            )

        products: list[
            ProductCandidate
        ] = []

        for item in raw_products:
            if not isinstance(item, dict):
                continue

            key = item.get("key")
            title = item.get("title")
            url = item.get("url")

            if all(
                isinstance(value, str)
                for value in (
                    key,
                    title,
                    url,
                )
            ):
                products.append(
                    ProductCandidate(
                        key=key,
                        title=title,
                        url=url,
                    )
                )

        return products

    def _write_index(
        self,
        payload: dict,
    ) -> None:
        """Сохраняет индекс на диск."""

        self._index_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._index_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )