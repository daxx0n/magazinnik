from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def clean_catalog_service() -> None:
    path = ROOT / "app/services/catalog_service.py"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(?:    @synchronized\n)?"
        r"    async def ingest_offers_with_report_async\(.*?"
        r"(?=    @synchronized\n"
        r"    def ingest_external_items_with_report\()",
        re.DOTALL,
    )
    block = '''    async def ingest_offers_with_report_async(
        self,
        offers: Iterable[ProductOffer],
    ) -> CatalogIngestReport:
        """Сохраняет каталог вне event loop, сериализуя конкурентные записи."""

        offer_tuple = tuple(offers)
        return await asyncio.to_thread(
            self.ingest_offers_with_report,
            offer_tuple,
        )

'''
    text, count = pattern.subn(block, text, count=1)
    if count != 1:
        raise RuntimeError("Unable to normalize async catalog ingest")
    path.write_text(text, encoding="utf-8")


def deduplicate(text: str, block: str, label: str) -> str:
    count = text.count(block)
    if count < 1:
        raise RuntimeError(f"Missing block: {label}")
    while block + block in text:
        text = text.replace(block + block, block)
    if text.count(block) != 1:
        raise RuntimeError(f"Unable to deduplicate block: {label}")
    return text


def clean_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text(encoding="utf-8")
    semaphore = '''        self._source_search_semaphore = asyncio.Semaphore(
            self._positive_environment_int(
                "SOURCE_SEARCH_MAX_CONCURRENCY",
                12,
            )
        )
'''
    positive_int = '''    @staticmethod
    def _positive_environment_int(name: str, default: int) -> int:
        try:
            value = int(os.getenv(name, "").strip())
        except ValueError:
            return default
        return value if value > 0 else default

'''
    limited_loader = '''    async def _run_limited_source_loader(
        self,
        loader: Callable[[], Awaitable[list[SearchItem]]],
    ) -> list[SearchItem]:
        async with self._source_search_semaphore:
            return await loader()

'''
    text = deduplicate(text, semaphore, "source semaphore")
    text = deduplicate(text, positive_int, "positive environment integer")
    text = deduplicate(text, limited_loader, "limited source loader")
    path.write_text(text, encoding="utf-8")


def clean_price_history() -> None:
    path = ROOT / "app/services/price_history.py"
    text = path.read_text(encoding="utf-8")
    if "from contextlib import contextmanager\n" not in text:
        text = text.replace(
            "import sqlite3\n",
            "import sqlite3\nfrom contextlib import contextmanager\n",
            1,
        )
    text = text.replace(
        "with self._connect() as connection:",
        "with self._connection() as connection:",
    )
    marker = "    def _connect(self) -> sqlite3.Connection:\n"
    context_method = '''    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

'''
    if context_method not in text:
        if marker not in text:
            raise RuntimeError("Missing SQLite connection marker")
        text = text.replace(marker, context_method + marker, 1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    clean_catalog_service()
    clean_price_service()
    clean_price_history()


if __name__ == "__main__":
    main()
