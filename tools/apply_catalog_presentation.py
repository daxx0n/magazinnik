from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    file_path = ROOT / path
    content = file_path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one occurrence in {path}, found {count}: {old[:80]!r}"
        )
    file_path.write_text(content.replace(old, new, 1), encoding="utf-8")


def write(path: str, content: str) -> None:
    file_path = ROOT / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


replace_once(
    "app/models/search_result.py",
    '    completed_at: str = ""\n    product_key: str = ""\n',
    '    completed_at: str = ""\n'
    '    product_key: str = ""\n'
    '    master_product_key: str = ""\n'
    '    master_product_title: str = ""\n'
    '    catalog_presentation: bool = False\n',
)

replace_once(
    "app/services/catalog_service.py",
    '    def search(self, query: str) -> list[MasterCatalogProduct]:\n'
    '        return self._catalog.search(query)\n\n'
    '    def save(self) -> None:\n',
    '    def search(self, query: str) -> list[MasterCatalogProduct]:\n'
    '        return self._catalog.search(query)\n\n'
    '    def get_product(\n'
    '        self,\n'
    '        product_key: str,\n'
    '    ) -> MasterCatalogProduct | None:\n'
    '        """Возвращает мастер-карточку по стабильному ключу."""\n\n'
    '        return next(\n'
    '            (\n'
    '                product\n'
    '                for product in self._catalog.products\n'
    '                if product.key == product_key\n'
    '            ),\n'
    '            None,\n'
    '        )\n\n'
    '    def save(self) -> None:\n',
)

replace_once(
    "app/services/price_service.py",
    "import logging\nimport re\n",
    "import logging\nimport os\nimport re\n",
)

replace_once(
    "app/services/price_service.py",
    "from app.models.category import ProductCategory\n",
    "from app.models.catalog import (\n"
    "    CatalogIngestReport,\n"
    "    MasterCatalogProduct,\n"
    ")\n"
    "from app.models.category import ProductCategory\n",
)

replace_once(
    "app/services/price_service.py",
    '    def __init__(\n'
    '        self,\n'
    '        catalog_service: CatalogService | None = None,\n'
    '    ) -> None:\n',
    '    def __init__(\n'
    '        self,\n'
    '        catalog_service: CatalogService | None = None,\n'
    '        catalog_presentation_enabled: bool | None = None,\n'
    '    ) -> None:\n',
)

replace_once(
    "app/services/price_service.py",
    '        self._zeon_source = ZeonSource()\n'
    '        self._catalog_service = catalog_service or CatalogService()\n\n'
    '        self._source_search_cache: OrderedDict[\n',
    '        self._zeon_source = ZeonSource()\n'
    '        self._catalog_service = catalog_service or CatalogService()\n'
    '        self._catalog_presentation_enabled = (\n'
    '            catalog_presentation_enabled\n'
    '            if catalog_presentation_enabled is not None\n'
    '            else self._env_flag(\n'
    '                "MASTER_CATALOG_PRESENTATION_ENABLED"\n'
    '            )\n'
    '        )\n\n'
    '        self._source_search_cache: OrderedDict[\n',
)

replace_once(
    "app/services/price_service.py",
    '        self._ingest_catalog_offers(combined_offers)\n'
    '        offers = self._prepare_aggregate_offers(\n'
    '            offers=combined_offers,\n'
    '        )\n\n'
    '        return ComparisonResult(\n',
    '        catalog_report = self._ingest_catalog_offers(\n'
    '            combined_offers\n'
    '        )\n'
    '        master_product = self._master_product_for_report(\n'
    '            catalog_report\n'
    '        )\n'
    '        offers = self._prepare_aggregate_offers(\n'
    '            offers=combined_offers,\n'
    '        )\n\n'
    '        return ComparisonResult(\n',
)

replace_once(
    "app/services/price_service.py",
    '            completed_at=datetime.now().strftime(\n'
    '                "%d.%m.%Y %H:%M:%S"\n'
    '            ),\n'
    '            product_key=product_key,\n'
    '        )\n\n'
    '    def _ingest_catalog_offers(\n',
    '            completed_at=datetime.now().strftime(\n'
    '                "%d.%m.%Y %H:%M:%S"\n'
    '            ),\n'
    '            product_key=product_key,\n'
    '            master_product_key=(\n'
    '                master_product.key\n'
    '                if master_product is not None\n'
    '                else ""\n'
    '            ),\n'
    '            master_product_title=(\n'
    '                master_product.title\n'
    '                if master_product is not None\n'
    '                else ""\n'
    '            ),\n'
    '            catalog_presentation=(\n'
    '                master_product is not None\n'
    '            ),\n'
    '        )\n\n'
    '    def _ingest_catalog_offers(\n',
)

replace_once(
    "app/services/price_service.py",
    '    def _ingest_catalog_offers(\n'
    '        self,\n'
    '        offers: Iterable[ProductOffer],\n'
    '    ) -> None:\n'
    '        """Обновляет мастер-каталог, не влияя на основной поиск."""\n\n'
    '        try:\n'
    '            report = (\n'
    '                self._catalog_service\n'
    '                .ingest_offers_with_report(offers)\n'
    '            )\n'
    '        except Exception:\n'
    '            logger.exception(\n'
    '                "Master catalog shadow ingest failed"\n'
    '            )\n'
    '            return\n\n'
    '        logger.info(\n'
    '            "Master catalog shadow ingest: total=%d "\n'
    '            "created=%d merged=%d updated=%d products=%d",\n'
    '            report.total_offers,\n'
    '            report.created_products,\n'
    '            report.merged_offers,\n'
    '            report.updated_offers,\n'
    '            len(report.product_keys),\n'
    '        )\n\n'
    '    @staticmethod\n'
    '    async def _timed_result(\n',
    '    def _ingest_catalog_offers(\n'
    '        self,\n'
    '        offers: Iterable[ProductOffer],\n'
    '    ) -> CatalogIngestReport | None:\n'
    '        """Обновляет мастер-каталог, не влияя на основной поиск."""\n\n'
    '        try:\n'
    '            report = (\n'
    '                self._catalog_service\n'
    '                .ingest_offers_with_report(offers)\n'
    '            )\n'
    '        except Exception:\n'
    '            logger.exception(\n'
    '                "Master catalog shadow ingest failed"\n'
    '            )\n'
    '            return None\n\n'
    '        logger.info(\n'
    '            "Master catalog shadow ingest: total=%d "\n'
    '            "created=%d merged=%d updated=%d products=%d",\n'
    '            report.total_offers,\n'
    '            report.created_products,\n'
    '            report.merged_offers,\n'
    '            report.updated_offers,\n'
    '            len(report.product_keys),\n'
    '        )\n'
    '        return report\n\n'
    '    def _master_product_for_report(\n'
    '        self,\n'
    '        report: CatalogIngestReport | None,\n'
    '    ) -> MasterCatalogProduct | None:\n'
    '        """Включает мастер-представление только при одном совпадении."""\n\n'
    '        if (\n'
    '            not self._catalog_presentation_enabled\n'
    '            or report is None\n'
    '            or len(report.product_keys) != 1\n'
    '        ):\n'
    '            return None\n\n'
    '        try:\n'
    '            return self._catalog_service.get_product(\n'
    '                report.product_keys[0]\n'
    '            )\n'
    '        except Exception:\n'
    '            logger.exception(\n'
    '                "Master catalog presentation read failed"\n'
    '            )\n'
    '            return None\n\n'
    '    @staticmethod\n'
    '    def _env_flag(name: str) -> bool:\n'
    '        return os.getenv(name, "").strip().casefold() in {\n'
    '            "1",\n'
    '            "true",\n'
    '            "yes",\n'
    '            "on",\n'
    '        }\n\n'
    '    @staticmethod\n'
    '    async def _timed_result(\n',
)

replace_once(
    "app/handlers/search.py",
    '    await asyncio.to_thread(\n'
    '        get_price_history_repository().record_offers,\n'
    '        product_key,\n'
    '        comparison.product_title,\n'
    '        comparison.offers,\n'
    '    )\n\n'
    '    await show_comparison(\n'
    '        message=message,\n'
    '        offers=comparison.offers,\n'
    '        source_statuses=(\n'
    '            comparison.source_statuses\n'
    '        ),\n'
    '        product_key=product_key,\n'
    '    )\n',
    '    display_title = (\n'
    '        comparison.master_product_title\n'
    '        or comparison.product_title\n'
    '    )\n'
    '    await asyncio.to_thread(\n'
    '        get_price_history_repository().record_offers,\n'
    '        product_key,\n'
    '        display_title,\n'
    '        comparison.offers,\n'
    '    )\n\n'
    '    await show_comparison(\n'
    '        message=message,\n'
    '        offers=comparison.offers,\n'
    '        source_statuses=(\n'
    '            comparison.source_statuses\n'
    '        ),\n'
    '        product_key=product_key,\n'
    '        product_title=(\n'
    '            comparison.master_product_title\n'
    '            if comparison.catalog_presentation\n'
    '            else None\n'
    '        ),\n'
    '        grouped=comparison.catalog_presentation,\n'
    '    )\n',
)

replace_once(
    "app/handlers/search.py",
    '        comparison.product_title or cheapest.title,\n',
    '        (\n'
    '            comparison.master_product_title\n'
    '            or comparison.product_title\n'
    '            or cheapest.title\n'
    '        ),\n',
)

replace_once(
    "app/handlers/search.py",
    'async def show_comparison(\n'
    '    message: Message,\n'
    '    offers: list[ProductOffer],\n'
    '    source_statuses: (\n'
    '        list[SourceSearchStatus] | None\n'
    '    ) = None,\n'
    '    product_key: str | None = None,\n'
    ') -> None:\n',
    'async def show_comparison(\n'
    '    message: Message,\n'
    '    offers: list[ProductOffer],\n'
    '    source_statuses: (\n'
    '        list[SourceSearchStatus] | None\n'
    '    ) = None,\n'
    '    product_key: str | None = None,\n'
    '    product_title: str | None = None,\n'
    '    grouped: bool = False,\n'
    ') -> None:\n',
)

replace_once(
    "app/handlers/search.py",
    '    lines = [\n'
    '        "🏆 Сравнение цен",\n'
    '        f"Найдено предложений: {len(offers)}",\n'
    '        "",\n'
    '    ]\n',
    '    lines = ["🏆 Сравнение цен"]\n\n'
    '    if product_title:\n'
    '        lines.append(\n'
    '            f"📱 {display_product_title(product_title)}"\n'
    '        )\n\n'
    '    lines.extend(\n'
    '        [\n'
    '            f"Найдено предложений: {len(offers)}",\n'
    '            "",\n'
    '        ]\n'
    '    )\n',
)

replace_once(
    "app/handlers/search.py",
    '        lines.append(\n'
    '            f"📱 {display_product_title(offer.title)}"\n'
    '        )\n\n'
    '        lines.append(\n',
    '        if not grouped:\n'
    '            lines.append(\n'
    '                f"📱 {display_product_title(offer.title)}"\n'
    '            )\n\n'
    '        lines.append(\n',
)

replace_once(
    "app/handlers/search.py",
    '    lines.extend(\n'
    '        [\n'
    '            "Самая низкая заявленная цена:",\n'
    '            (\n'
    '                f"✅ {cheapest_offer.price:.2f} "\n'
    '                f"{cheapest_offer.currency} — "\n'
    '                f"{cheapest_offer.seller or cheapest_offer.source}"\n'
    '            ),\n'
    '            "",\n'
    '            (\n'
    '                "⚠️ Убедись, что ссылки ведут "\n'
    '                "на одинаковую модификацию товара."\n'
    '            ),\n'
    '        ]\n'
    '    )\n',
    '    lines.extend(\n'
    '        [\n'
    '            "Самая низкая заявленная цена:",\n'
    '            (\n'
    '                f"✅ {cheapest_offer.price:.2f} "\n'
    '                f"{cheapest_offer.currency} — "\n'
    '                f"{cheapest_offer.seller or cheapest_offer.source}"\n'
    '            ),\n'
    '            "",\n'
    '            (\n'
    '                "ℹ️ Предложения объединены в одну карточку "\n'
    '                "по модели и варианту товара."\n'
    '                if grouped\n'
    '                else (\n'
    '                    "⚠️ Убедись, что ссылки ведут "\n'
    '                    "на одинаковую модификацию товара."\n'
    '                )\n'
    '            ),\n'
    '        ]\n'
    '    )\n',
)

replace_once(
    "app/handlers/search.py",
    '                    comparison.product_title or alert.title,\n',
    '                    (\n'
    '                        comparison.master_product_title\n'
    '                        or comparison.product_title\n'
    '                        or alert.title\n'
    '                    ),\n',
)

replace_once(
    "app/handlers/search.py",
    '    product_title = comparison.product_title\n\n'
    '    if not product_title and comparison.offers:\n',
    '    product_title = (\n'
    '        comparison.master_product_title\n'
    '        or comparison.product_title\n'
    '    )\n\n'
    '    if not product_title and comparison.offers:\n',
)

replace_once(
    "app/handlers/search.py",
    '    if comparison.query:\n'
    '        lines.append(f"🔎 Запрос: {comparison.query}")\n',
    '    if comparison.catalog_presentation:\n'
    '        lines.append(\n'
    '            "🧩 Мастер-карточка: "\n'
    '            f"{comparison.master_product_key or \'без ключа\'}"\n'
    '        )\n\n'
    '    if comparison.query:\n'
    '        lines.append(f"🔎 Запрос: {comparison.query}")\n',
)

write(
    "tests/test_price_service_catalog.py",
    '''import os\nimport unittest\nfrom unittest.mock import AsyncMock, Mock, patch\n\nfrom app.models.catalog import MasterCatalogProduct, ProductIdentity\nfrom app.models.offer import ProductOffer\nfrom app.services.price_service import PriceService\n\n\ndef make_offer(\n    source: str,\n    title: str,\n    price: float,\n    suffix: str,\n) -> ProductOffer:\n    return ProductOffer(\n        source=source,\n        title=title,\n        price=price,\n        currency="BYN",\n        available=True,\n        url=f"https://example.com/{suffix}",\n    )\n\n\nclass PriceServiceCatalogShadowTest(unittest.IsolatedAsyncioTestCase):\n    canonical = "Духовой шкаф Bosch HBA534EB3"\n\n    def build_service(\n        self,\n        catalog_service: Mock,\n        *,\n        presentation_enabled: bool = False,\n    ) -> PriceService:\n        service = PriceService(\n            catalog_service=catalog_service,\n            catalog_presentation_enabled=presentation_enabled,\n        )\n        service._onliner_queries["bosch"] = "Bosch HBA534EB3"\n        service.search_onliner_key = AsyncMock(\n            return_value=[\n                make_offer(\n                    "Onliner",\n                    self.canonical,\n                    1500,\n                    "onliner-1",\n                ),\n                make_offer(\n                    "Onliner",\n                    self.canonical,\n                    1550,\n                    "onliner-2",\n                ),\n            ]\n        )\n        service._search_five_element_by_query = AsyncMock(\n            return_value=(\n                [\n                    make_offer(\n                        "5 элемент",\n                        self.canonical,\n                        1490,\n                        "five",\n                    )\n                ],\n                True,\n                [],\n            )\n        )\n        service._search_twenty_one_vek_by_query = AsyncMock(\n            return_value=[\n                make_offer(\n                    "21vek",\n                    self.canonical,\n                    1450,\n                    "twenty-one",\n                ),\n                make_offer(\n                    "21vek",\n                    "Apple iPhone 17 Pro 256GB",\n                    100,\n                    "rejected",\n                ),\n            ]\n        )\n        service._search_shop_by_query = AsyncMock(return_value=[])\n        service._search_electrosila_query = AsyncMock(return_value=[])\n        service._search_zeon_query = AsyncMock(return_value=[])\n        return service\n\n    @staticmethod\n    def master_product() -> MasterCatalogProduct:\n        return MasterCatalogProduct(\n            key="product-1",\n            title="Bosch HBA534EB3",\n            identity=ProductIdentity(\n                brand="bosch",\n                model="hba534eb3",\n            ),\n        )\n\n    async def test_ingests_all_accepted_offers_only(self) -> None:\n        catalog_service = Mock()\n        catalog_service.ingest_offers_with_report.return_value = Mock(\n            total_offers=4,\n            created_products=1,\n            merged_offers=3,\n            updated_offers=0,\n            product_keys=("product-1",),\n        )\n        service = self.build_service(catalog_service)\n\n        result = await service.search_all_sources_by_onliner_key("bosch")\n\n        catalog_service.ingest_offers_with_report.assert_called_once()\n        ingested = list(\n            catalog_service.ingest_offers_with_report.call_args.args[0]\n        )\n        self.assertEqual(len(ingested), 4)\n        self.assertEqual(\n            {offer.url for offer in ingested},\n            {\n                "https://example.com/onliner-1",\n                "https://example.com/onliner-2",\n                "https://example.com/five",\n                "https://example.com/twenty-one",\n            },\n        )\n        self.assertNotIn(\n            "https://example.com/rejected",\n            {offer.url for offer in ingested},\n        )\n        self.assertEqual(\n            [offer.source for offer in result.offers],\n            ["21vek", "5 элемент", "Onliner"],\n        )\n        self.assertFalse(result.catalog_presentation)\n        catalog_service.get_product.assert_not_called()\n\n    async def test_enables_master_presentation_for_one_product(self) -> None:\n        catalog_service = Mock()\n        catalog_service.ingest_offers_with_report.return_value = Mock(\n            total_offers=4,\n            created_products=1,\n            merged_offers=3,\n            updated_offers=0,\n            product_keys=("product-1",),\n        )\n        catalog_service.get_product.return_value = self.master_product()\n        service = self.build_service(\n            catalog_service,\n            presentation_enabled=True,\n        )\n\n        result = await service.search_all_sources_by_onliner_key("bosch")\n\n        self.assertTrue(result.catalog_presentation)\n        self.assertEqual(result.master_product_key, "product-1")\n        self.assertEqual(result.master_product_title, "Bosch HBA534EB3")\n        catalog_service.get_product.assert_called_once_with("product-1")\n\n    async def test_keeps_legacy_view_for_ambiguous_catalog_result(self) -> None:\n        catalog_service = Mock()\n        catalog_service.ingest_offers_with_report.return_value = Mock(\n            total_offers=4,\n            created_products=2,\n            merged_offers=2,\n            updated_offers=0,\n            product_keys=("product-1", "product-2"),\n        )\n        service = self.build_service(\n            catalog_service,\n            presentation_enabled=True,\n        )\n\n        result = await service.search_all_sources_by_onliner_key("bosch")\n\n        self.assertFalse(result.catalog_presentation)\n        self.assertEqual(result.master_product_key, "")\n        catalog_service.get_product.assert_not_called()\n\n    async def test_catalog_failure_does_not_break_search(self) -> None:\n        catalog_service = Mock()\n        catalog_service.ingest_offers_with_report.side_effect = RuntimeError(\n            "catalog unavailable"\n        )\n        service = self.build_service(\n            catalog_service,\n            presentation_enabled=True,\n        )\n\n        with self.assertLogs(\n            "app.services.price_service",\n            level="ERROR",\n        ) as captured:\n            result = await service.search_all_sources_by_onliner_key(\n                "bosch"\n            )\n\n        self.assertEqual(len(result.offers), 3)\n        self.assertFalse(result.catalog_presentation)\n        self.assertTrue(\n            any(\n                "Master catalog shadow ingest failed" in message\n                for message in captured.output\n            )\n        )\n\n    async def test_catalog_read_failure_keeps_legacy_view(self) -> None:\n        catalog_service = Mock()\n        catalog_service.ingest_offers_with_report.return_value = Mock(\n            total_offers=4,\n            created_products=1,\n            merged_offers=3,\n            updated_offers=0,\n            product_keys=("product-1",),\n        )\n        catalog_service.get_product.side_effect = RuntimeError("read failed")\n        service = self.build_service(\n            catalog_service,\n            presentation_enabled=True,\n        )\n\n        with self.assertLogs(\n            "app.services.price_service",\n            level="ERROR",\n        ):\n            result = await service.search_all_sources_by_onliner_key(\n                "bosch"\n            )\n\n        self.assertFalse(result.catalog_presentation)\n        self.assertEqual(result.master_product_title, "")\n\n    def test_reads_presentation_flag_from_environment(self) -> None:\n        with patch.dict(\n            os.environ,\n            {"MASTER_CATALOG_PRESENTATION_ENABLED": "true"},\n            clear=False,\n        ):\n            service = PriceService(catalog_service=Mock())\n\n        self.assertTrue(service._catalog_presentation_enabled)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
)

write(
    "tests/test_catalog_presentation.py",
    '''import unittest\nfrom unittest.mock import AsyncMock\n\nfrom app.handlers.search import (\n    format_comparison_diagnostics,\n    show_comparison,\n)\nfrom app.models.offer import ProductOffer\nfrom app.models.search_result import ComparisonResult\n\n\ndef offer(source: str, title: str, price: float) -> ProductOffer:\n    return ProductOffer(\n        source=source,\n        title=title,\n        price=price,\n        currency="BYN",\n        available=True,\n        url=f"https://example.com/{source}",\n    )\n\n\nclass CatalogPresentationTest(unittest.IsolatedAsyncioTestCase):\n    async def test_grouped_comparison_shows_one_master_title(self) -> None:\n        message = AsyncMock()\n        offers = [\n            offer("21vek", "Духовой шкаф Bosch HBA 534 EB3", 1400),\n            offer("Onliner", "Bosch HBA534EB3", 1500),\n        ]\n\n        await show_comparison(\n            message=message,\n            offers=offers,\n            product_title="Bosch HBA534EB3",\n            grouped=True,\n        )\n\n        text = message.edit_text.call_args.args[0]\n        self.assertEqual(text.count("📱"), 1)\n        self.assertIn("📱 Bosch HBA534EB3", text)\n        self.assertIn("21vek", text)\n        self.assertIn("Onliner", text)\n        self.assertIn(\n            "Предложения объединены в одну карточку",\n            text,\n        )\n        self.assertNotIn(\n            "Убедись, что ссылки ведут",\n            text,\n        )\n\n    async def test_legacy_comparison_keeps_offer_titles(self) -> None:\n        message = AsyncMock()\n        offers = [\n            offer("21vek", "Bosch HBA 534 EB3", 1400),\n            offer("Onliner", "Bosch HBA534EB3", 1500),\n        ]\n\n        await show_comparison(message=message, offers=offers)\n\n        text = message.edit_text.call_args.args[0]\n        self.assertEqual(text.count("📱"), 2)\n        self.assertIn("Убедись, что ссылки ведут", text)\n\n    def test_diagnostics_exposes_master_product(self) -> None:\n        comparison = ComparisonResult(\n            offers=[offer("Onliner", "Bosch HBA534EB3", 1500)],\n            source_statuses=[],\n            match_decisions=[],\n            product_title="Духовой шкаф Bosch HBA534EB3",\n            master_product_key="product-7",\n            master_product_title="Bosch HBA534EB3",\n            catalog_presentation=True,\n        )\n\n        text = format_comparison_diagnostics(comparison)\n\n        self.assertIn("📱 Bosch HBA534EB3", text)\n        self.assertIn("🧩 Мастер-карточка: product-7", text)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
)

write(
    "tests/test_catalog_lookup.py",
    '''import unittest\n\nfrom app.models.offer import ProductOffer\nfrom app.services.catalog_service import CatalogService\n\n\nclass CatalogLookupTest(unittest.TestCase):\n    def test_returns_product_by_stable_key(self) -> None:\n        service = CatalogService()\n        product = service.ingest_offer(\n            ProductOffer(\n                source="Onliner",\n                title="Bosch HBA534EB3",\n                price=1500,\n                currency="BYN",\n                available=True,\n                url="https://example.com/bosch",\n            )\n        )\n\n        self.assertIs(service.get_product(product.key), product)\n        self.assertIsNone(service.get_product("missing"))\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
)
