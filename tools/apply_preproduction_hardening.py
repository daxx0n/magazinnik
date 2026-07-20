from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f"Missing replacement target: {label}")


def patch_catalog_service() -> None:
    path = ROOT / "app/services/catalog_service.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import logging\nimport os\n",
        "import asyncio\nimport logging\nimport os\nimport threading\nfrom functools import wraps\n",
        "catalog imports",
    )
    marker = "CatalogStorage = JsonCatalogStorage | SqliteCatalogStorage\n\n\n"
    decorator = '''CatalogStorage = JsonCatalogStorage | SqliteCatalogStorage\n\n\ndef synchronized(method):\n    """Сериализует доступ к общему in-memory каталогу из event loop и threads."""\n\n    @wraps(method)\n    def wrapper(self, *args, **kwargs):\n        with self._lock:\n            return method(self, *args, **kwargs)\n\n    return wrapper\n\n\n'''
    text = replace_once(text, marker, decorator, "catalog lock decorator")
    text = replace_once(
        text,
        "        self._metrics = CatalogMetrics()\n\n        if self._storage is not None and restore_on_start:\n",
        "        self._metrics = CatalogMetrics()\n        self._lock = threading.RLock()\n\n        if self._storage is not None and restore_on_start:\n",
        "catalog lock init",
    )
    for signature in (
        "    def ingest_offer(self, offer: ProductOffer) -> MasterCatalogProduct:\n",
        "    def ingest_offers(\n",
        "    def ingest_offers_with_report(\n",
        "    def ingest_external_items_with_report(\n",
        "    def search(self, query: str) -> list[MasterCatalogProduct]:\n",
        "    def get_product(\n",
        "    def snapshot_metrics(\n",
        "    def pending_reviews(self, limit: int = 20) -> tuple[MatchReview, ...]:\n",
        "    def accept_review(\n",
        "    def reject_review(\n",
        "    def save(self) -> None:\n",
    ):
        text = replace_once(
            text,
            signature,
            "    @synchronized\n" + signature,
            f"synchronize {signature.strip()}",
        )
    async_method = '''    async def ingest_offers_with_report_async(\n        self,\n        offers: Iterable[ProductOffer],\n    ) -> CatalogIngestReport:\n        """Сохраняет каталог вне event loop, сериализуя конкурентные записи."""\n\n        offer_tuple = tuple(offers)\n        return await asyncio.to_thread(\n            self.ingest_offers_with_report,\n            offer_tuple,\n        )\n\n'''
    text = replace_once(
        text,
        "    def ingest_external_items_with_report(\n",
        async_method + "    @synchronized\n    def ingest_external_items_with_report(\n",
        "async catalog ingest",
    )
    text = text.replace(
        "    @synchronized\n    @synchronized\n",
        "    @synchronized\n",
    )
    path.write_text(text, encoding="utf-8")


def patch_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    async def search_all_sources_by_onliner_key(\n        self,\n        product_key: str,\n    ) -> ComparisonResult:\n",
        "    async def search_all_sources_by_onliner_key(\n        self,\n        product_key: str,\n        original_query: str | None = None,\n    ) -> ComparisonResult:\n",
        "aggregate signature",
    )
    text = replace_once(
        text,
        "        original_query = self._onliner_queries.get(\n            product_key,\n            canonical_title,\n        )\n",
        "        original_query = original_query or self._onliner_queries.get(\n            product_key,\n            canonical_title,\n        )\n",
        "explicit original query",
    )
    text = replace_once(
        text,
        "        catalog_report = self._ingest_catalog_offers(\n            combined_offers\n        )\n",
        "        catalog_report = await self._ingest_catalog_offers(\n            combined_offers\n        )\n",
        "await catalog ingest",
    )
    text = replace_once(
        text,
        "    def _ingest_catalog_offers(\n        self,\n        offers: Iterable[ProductOffer],\n    ) -> CatalogIngestReport | None:\n",
        "    async def _ingest_catalog_offers(\n        self,\n        offers: Iterable[ProductOffer],\n    ) -> CatalogIngestReport | None:\n",
        "async catalog ingest signature",
    )
    text = replace_once(
        text,
        "                self._catalog_service\n                .ingest_offers_with_report(offers)\n",
        "                await self._catalog_service\n                .ingest_offers_with_report_async(offers)\n",
        "async catalog call",
    )
    text = replace_once(
        text,
        "        self._source_search_tasks: dict[\n            tuple[str, str, int],\n            asyncio.Task[list[Any]],\n        ] = {}\n",
        "        self._source_search_tasks: dict[\n            tuple[str, str, int],\n            asyncio.Task[list[Any]],\n        ] = {}\n        self._source_search_semaphore = asyncio.Semaphore(\n            self._positive_environment_int(\n                \"SOURCE_SEARCH_MAX_CONCURRENCY\",\n                12,\n            )\n        )\n",
        "source semaphore init",
    )
    text = replace_once(
        text,
        "            task = asyncio.create_task(loader())\n",
        "            task = asyncio.create_task(\n                self._run_limited_source_loader(loader)\n            )\n",
        "limited source task",
    )
    limited_method = '''    async def _run_limited_source_loader(\n        self,\n        loader: Callable[[], Awaitable[list[SearchItem]]],\n    ) -> list[SearchItem]:\n        async with self._source_search_semaphore:\n            return await loader()\n\n'''
    text = replace_once(
        text,
        "    def _complete_source_search(\n",
        limited_method + "    def _complete_source_search(\n",
        "limited source loader",
    )
    env_method = '''    @staticmethod\n    def _positive_environment_int(name: str, default: int) -> int:\n        try:\n            value = int(os.getenv(name, "").strip())\n        except ValueError:\n            return default\n        return value if value > 0 else default\n\n'''
    text = replace_once(
        text,
        "    @staticmethod\n    async def _timed_result(\n",
        env_method + "    @staticmethod\n    async def _timed_result(\n",
        "positive environment int",
    )
    path.write_text(text, encoding="utf-8")


def patch_catalog_first_search() -> None:
    path = ROOT / "app/services/catalog_first_search.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    async def search_all_sources_by_onliner_key(\n        self,\n        product_key: str,\n    ) -> ComparisonResult:\n",
        "    async def search_all_sources_by_onliner_key(\n        self,\n        product_key: str,\n        original_query: str | None = None,\n    ) -> ComparisonResult:\n",
        "catalog-first signature",
    )
    text = replace_once(
        text,
        "            return await super().search_all_sources_by_onliner_key(product_key)\n",
        "            return await super().search_all_sources_by_onliner_key(\n                product_key,\n                original_query=original_query,\n            )\n",
        "catalog-first passthrough",
    )
    text = replace_once(
        text,
        "        query = self._catalog_queries.get(product_key, product.title)\n",
        "        query = original_query or self._catalog_queries.get(\n            product_key,\n            product.title,\n        )\n",
        "catalog explicit query",
    )
    text = replace_once(
        text,
        "                result = await super().search_all_sources_by_onliner_key(\n                    live_candidate.key\n                )\n",
        "                result = await super().search_all_sources_by_onliner_key(\n                    live_candidate.key,\n                    original_query=query,\n                )\n",
        "catalog live query",
    )
    path.write_text(text, encoding="utf-8")


def patch_search_handler() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from app.services.price_history import PriceHistoryRepository\n",
        "from app.services.price_history import PriceHistoryRepository\nfrom app.services.search_input import SearchInputError, normalize_search_query\nfrom app.services.search_load import (\n    SearchBusyError,\n    SearchRequestCoordinator,\n)\nfrom app.services.search_sessions import (\n    SearchSessionRegistry,\n    SelectionQueryRegistry,\n)\n",
        "search infrastructure imports",
    )
    text = replace_once(
        text,
        "MAX_SEARCH_SESSIONS = 100\nMAX_DIAGNOSTIC_SESSIONS = 1_000\n",
        "MAX_SEARCH_SESSIONS = 1_000\nMAX_DIAGNOSTIC_SESSIONS = 1_000\nSEARCH_SESSION_TTL_SECONDS = 1_800.0\n",
        "session limits",
    )
    text = replace_once(
        text,
        "price_history_repository: PriceHistoryRepository | None = None\n",
        "price_history_repository: PriceHistoryRepository | None = None\nproduct_session_registry = SearchSessionRegistry(\n    capacity=MAX_SEARCH_SESSIONS,\n    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,\n)\ncategory_session_registry = SearchSessionRegistry(\n    capacity=MAX_SEARCH_SESSIONS,\n    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,\n)\nselection_query_registry = SelectionQueryRegistry(\n    capacity=10_000,\n    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,\n)\ncomparison_coordinator: SearchRequestCoordinator[\n    tuple[str, str],\n    ComparisonResult,\n] = SearchRequestCoordinator()\n",
        "session registries",
    )
    text = text.replace(
        "comparison_diagnostics: OrderedDict[\n    int,\n    ComparisonResult,\n] = OrderedDict()",
        "comparison_diagnostics: OrderedDict[\n    tuple[int, int | None],\n    ComparisonResult,\n] = OrderedDict()",
    )
    text = replace_once(
        text,
        "    chat_id = message_chat_id(message)\n    comparison = (\n        comparison_diagnostics.get(chat_id)\n        if chat_id is not None\n        else None\n    )\n",
        "    interaction_key = message_interaction_key(message)\n    comparison = (\n        comparison_diagnostics.get(interaction_key)\n        if interaction_key is not None\n        else None\n    )\n",
        "diagnostics user isolation",
    )
    text = replace_once(
        text,
        "    chat_id = message_chat_id(callback.message)\n    product_key = (callback.data or \"\").removeprefix(\n",
        "    chat_id = message_chat_id(callback.message)\n    user_id = callback_user_id(callback)\n    product_key = (callback.data or \"\").removeprefix(\n",
        "alert user id",
    )
    text = replace_once(
        text,
        "        comparison_diagnostics.get(chat_id)\n        if chat_id is not None\n",
        "        comparison_diagnostics.get((chat_id, user_id))\n        if chat_id is not None\n",
        "alert diagnostics isolation",
    )
    text = replace_once(
        text,
        "    await load_product_comparison(\n        message=callback.message,\n        product_key=product_key,\n    )\n",
        "    chat_id = message_chat_id(callback.message)\n    user_id = callback_user_id(callback)\n    original_query = selection_query_registry.get(\n        chat_id=chat_id,\n        user_id=user_id,\n        product_key=product_key,\n    )\n    await load_product_comparison(\n        message=callback.message,\n        product_key=product_key,\n        original_query=original_query,\n    )\n",
        "selection query context",
    )
    text = replace_once(
        text,
        "async def load_product_comparison(\n    message: Message,\n    product_key: str,\n) -> None:\n",
        "async def load_product_comparison(\n    message: Message,\n    product_key: str,\n    original_query: str | None = None,\n) -> None:\n",
        "comparison loader signature",
    )
    text = replace_once(
        text,
        "        comparison = (\n            await price_service\n            .search_all_sources_by_onliner_key(\n                product_key\n            )\n        )\n",
        "        comparison = await comparison_coordinator.run(\n            (product_key, original_query or \"\"),\n            lambda: price_service.search_all_sources_by_onliner_key(\n                product_key,\n                original_query=original_query,\n            ),\n        )\n",
        "coordinated comparison",
    )
    text = replace_once(
        text,
        "    except ProductNotFoundError as error:\n",
        "    except SearchBusyError:\n        await message.edit_text(\n            \"Сейчас выполняется слишком много сравнений. \"\n            \"Попробуй ещё раз через несколько секунд.\"\n        )\n        return\n    except ProductNotFoundError as error:\n",
        "busy comparison response",
    )
    text = replace_once(
        text,
        "        store_comparison_diagnostics(\n            chat_id=chat_id,\n            comparison=comparison,\n        )\n",
        "        store_comparison_diagnostics(\n            chat_id=chat_id,\n            user_id=message_user_id(message),\n            comparison=comparison,\n        )\n",
        "store isolated diagnostics",
    )
    text = replace_once(
        text,
        "    query = (message.text or \"\").strip()\n\n    if query.startswith(\"/\"):\n",
        "    raw_query = (message.text or \"\").strip()\n\n    if raw_query.startswith(\"/\"):\n",
        "raw query",
    )
    text = replace_once(
        text,
        "    if len(query) < 3:\n        await message.answer(\n            \"Название слишком короткое.\\n\"\n            \"Укажи модель товара.\"\n        )\n        return\n\n    status_message = await message.answer(\n",
        "    try:\n        query = normalize_search_query(raw_query)\n    except SearchInputError as error:\n        await message.answer(str(error))\n        return\n\n    status_message = await message.answer(\n",
        "normalized query",
    )
    text = replace_once(
        text,
        "            category_search_id = store_category_search(\n                query=query,\n                categories=categories,\n            )\n",
        "            category_search_id = store_category_search(\n                query=query,\n                categories=categories,\n                owner_chat_id=message_chat_id(message),\n                owner_user_id=message_user_id(message),\n            )\n",
        "owned category session",
    )
    text = replace_once(
        text,
        "    search_id = store_product_search(products)\n",
        "    search_id = store_product_search(\n        products,\n        query=query,\n        owner_chat_id=message_chat_id(message),\n        owner_user_id=message_user_id(message),\n    )\n",
        "owned product session",
    )
    text = replace_once(
        text,
        "    search_id = store_product_search(\n        products,\n        parent=(category_search_id, category_page),\n    )\n",
        "    search_id = store_product_search(\n        products,\n        parent=(category_search_id, category_page),\n        query=session.query,\n        owner_chat_id=message_chat_id(callback.message),\n        owner_user_id=callback_user_id(callback),\n    )\n",
        "owned category product session",
    )
    text = text.replace(
        "    products = product_searches.get(search_id)\n",
        "    products = authorized_product_search(callback, search_id)\n",
    )
    text = text.replace(
        "    session = category_searches.get(search_id)\n",
        "    session = authorized_category_search(callback, search_id)\n",
    )
    text = text.replace(
        "    session = category_searches.get(category_search_id)\n",
        "    session = authorized_category_search(\n        callback,\n        category_search_id,\n    )\n",
    )
    text = replace_once(
        text,
        "def store_product_search(\n    products: list[ProductCandidate],\n    parent: tuple[str, int] | None = None,\n) -> str:\n",
        "def store_product_search(\n    products: list[ProductCandidate],\n    parent: tuple[str, int] | None = None,\n    query: str = \"\",\n    owner_chat_id: int | None = None,\n    owner_user_id: int | None = None,\n) -> str:\n",
        "product session signature",
    )
    text = replace_once(
        text,
        "    product_searches[search_id] = products\n    product_searches.move_to_end(search_id)\n",
        "    product_searches[search_id] = products\n    product_searches.move_to_end(search_id)\n    product_session_registry.register(\n        search_id,\n        query=query,\n        owner_chat_id=owner_chat_id,\n        owner_user_id=owner_user_id,\n    )\n    for product in products:\n        selection_query_registry.remember(\n            chat_id=owner_chat_id,\n            user_id=owner_user_id,\n            product_key=product.key,\n            query=query,\n        )\n",
        "product session metadata",
    )
    text = replace_once(
        text,
        "        product_search_parents.pop(expired_search_id, None)\n",
        "        product_search_parents.pop(expired_search_id, None)\n        product_session_registry.remove(expired_search_id)\n",
        "product session eviction",
    )
    text = replace_once(
        text,
        "def store_category_search(\n    query: str,\n    categories: list[ProductCategory],\n) -> str:\n",
        "def store_category_search(\n    query: str,\n    categories: list[ProductCategory],\n    owner_chat_id: int | None = None,\n    owner_user_id: int | None = None,\n) -> str:\n",
        "category session signature",
    )
    text = replace_once(
        text,
        "    category_searches.move_to_end(search_id)\n\n    while len(category_searches) > MAX_SEARCH_SESSIONS:\n        category_searches.popitem(last=False)\n",
        "    category_searches.move_to_end(search_id)\n    category_session_registry.register(\n        search_id,\n        query=query,\n        owner_chat_id=owner_chat_id,\n        owner_user_id=owner_user_id,\n    )\n\n    while len(category_searches) > MAX_SEARCH_SESSIONS:\n        expired_search_id, _ = category_searches.popitem(last=False)\n        category_session_registry.remove(expired_search_id)\n",
        "category session metadata",
    )
    text = replace_once(
        text,
        "                    await price_service.search_all_sources_by_onliner_key(\n                        alert.product_key\n                    )\n",
        "                    await comparison_coordinator.run(\n                        (alert.product_key, alert.query),\n                        lambda: price_service.search_all_sources_by_onliner_key(\n                            alert.product_key,\n                            original_query=alert.query,\n                        ),\n                    )\n",
        "coordinated alert search",
    )
    helpers = '''\n\ndef callback_user_id(callback: CallbackQuery) -> int | None:\n    user = getattr(callback, "from_user", None)\n    user_id = getattr(user, "id", None)\n    return user_id if isinstance(user_id, int) else None\n\n\ndef message_user_id(message: Message) -> int | None:\n    user = getattr(message, "from_user", None)\n    user_id = getattr(user, "id", None)\n    return user_id if isinstance(user_id, int) else None\n\n\ndef message_interaction_key(\n    message: Message,\n) -> tuple[int, int | None] | None:\n    chat_id = message_chat_id(message)\n    if chat_id is None:\n        return None\n    return chat_id, message_user_id(message)\n\n\ndef authorized_product_search(\n    callback: CallbackQuery,\n    search_id: str,\n) -> list[ProductCandidate] | None:\n    metadata = product_session_registry.authorize(\n        search_id,\n        chat_id=(\n            message_chat_id(callback.message)\n            if callback.message is not None\n            else None\n        ),\n        user_id=callback_user_id(callback),\n    )\n    products = product_searches.get(search_id)\n    if metadata is None or products is None:\n        if products is None:\n            product_session_registry.remove(search_id)\n        return None\n    product_searches.move_to_end(search_id)\n    return products\n\n\ndef authorized_category_search(\n    callback: CallbackQuery,\n    search_id: str,\n) -> CategorySearchSession | None:\n    metadata = category_session_registry.authorize(\n        search_id,\n        chat_id=(\n            message_chat_id(callback.message)\n            if callback.message is not None\n            else None\n        ),\n        user_id=callback_user_id(callback),\n    )\n    session = category_searches.get(search_id)\n    if metadata is None or session is None:\n        if session is None:\n            category_session_registry.remove(search_id)\n        return None\n    category_searches.move_to_end(search_id)\n    return session\n'''
    text = replace_once(
        text,
        "\ndef store_comparison_diagnostics(\n",
        helpers + "\n\ndef store_comparison_diagnostics(\n",
        "session authorization helpers",
    )
    text = replace_once(
        text,
        "def store_comparison_diagnostics(\n    chat_id: int,\n    comparison: ComparisonResult,\n) -> None:\n",
        "def store_comparison_diagnostics(\n    chat_id: int,\n    comparison: ComparisonResult,\n    user_id: int | None = None,\n) -> None:\n",
        "diagnostics signature",
    )
    text = replace_once(
        text,
        "    comparison_diagnostics[chat_id] = comparison\n    comparison_diagnostics.move_to_end(chat_id)\n",
        "    key = (chat_id, user_id)\n    comparison_diagnostics[key] = comparison\n    comparison_diagnostics.move_to_end(key)\n",
        "diagnostics key",
    )
    text = text.replace(
        '        "color": "цвет",\n',
        '        "color": "цвет",\n        "color_unknown": "цвет не указан",\n',
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_catalog_service()
    patch_price_service()
    patch_catalog_first_search()
    patch_search_handler()


if __name__ == "__main__":
    main()
