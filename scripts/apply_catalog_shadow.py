from pathlib import Path


PRICE_SERVICE_PATH = Path("app/services/price_service.py")
TEST_PATH = Path("tests/test_price_service_catalog.py")


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one {label} occurrence, found {count}"
        )
    return content.replace(old, new, 1)


def patch_price_service() -> None:
    content = PRICE_SERVICE_PATH.read_text(encoding="utf-8")

    content = replace_once(
        content,
        "from app.sources.zeon import ZeonSource\n"
        "from app.services.product_variants import (\n",
        "from app.sources.zeon import ZeonSource\n"
        "from app.services.catalog_service import CatalogService\n"
        "from app.services.product_variants import (\n",
        "catalog service import",
    )
    content = replace_once(
        content,
        "    def __init__(self) -> None:\n",
        "    def __init__(\n"
        "        self,\n"
        "        catalog_service: CatalogService | None = None,\n"
        "    ) -> None:\n",
        "PriceService constructor",
    )
    content = replace_once(
        content,
        "        self._zeon_source = ZeonSource()\n\n"
        "        self._source_search_cache: OrderedDict[\n",
        "        self._zeon_source = ZeonSource()\n"
        "        self._catalog_service = catalog_service or CatalogService()\n\n"
        "        self._source_search_cache: OrderedDict[\n",
        "catalog service initialization",
    )
    content = replace_once(
        content,
        "        offers = self._prepare_aggregate_offers(\n"
        "            offers=combined_offers,\n"
        "        )\n\n"
        "        return ComparisonResult(\n",
        "        self._ingest_catalog_offers(combined_offers)\n"
        "        offers = self._prepare_aggregate_offers(\n"
        "            offers=combined_offers,\n"
        "        )\n\n"
        "        return ComparisonResult(\n",
        "shadow ingest call",
    )
    content = replace_once(
        content,
        "    @staticmethod\n"
        "    async def _timed_result(\n",
        "    def _ingest_catalog_offers(\n"
        "        self,\n"
        "        offers: Iterable[ProductOffer],\n"
        "    ) -> None:\n"
        "        \"\"\"Обновляет мастер-каталог, не влияя на основной поиск.\"\"\"\n\n"
        "        try:\n"
        "            report = (\n"
        "                self._catalog_service\n"
        "                .ingest_offers_with_report(offers)\n"
        "            )\n"
        "        except Exception:\n"
        "            logger.exception(\n"
        "                \"Master catalog shadow ingest failed\"\n"
        "            )\n"
        "            return\n\n"
        "        logger.info(\n"
        "            \"Master catalog shadow ingest: total=%d \"\n"
        "            \"created=%d merged=%d updated=%d products=%d\",\n"
        "            report.total_offers,\n"
        "            report.created_products,\n"
        "            report.merged_offers,\n"
        "            report.updated_offers,\n"
        "            len(report.product_keys),\n"
        "        )\n\n"
        "    @staticmethod\n"
        "    async def _timed_result(\n",
        "shadow ingest helper",
    )

    PRICE_SERVICE_PATH.write_text(content, encoding="utf-8")


def write_integration_tests() -> None:
    TEST_PATH.write_text(
        '''import unittest
from unittest.mock import AsyncMock, Mock

from app.models.offer import ProductOffer
from app.services.price_service import PriceService


def make_offer(
    source: str,
    title: str,
    price: float,
    suffix: str,
) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{suffix}",
    )


class PriceServiceCatalogShadowTest(unittest.IsolatedAsyncioTestCase):
    canonical = "Духовой шкаф Bosch HBA534EB3"

    def build_service(self, catalog_service: Mock) -> PriceService:
        service = PriceService(catalog_service=catalog_service)
        service._onliner_queries["bosch"] = "Bosch HBA534EB3"
        service.search_onliner_key = AsyncMock(
            return_value=[
                make_offer(
                    "Onliner",
                    self.canonical,
                    1500,
                    "onliner-1",
                ),
                make_offer(
                    "Onliner",
                    self.canonical,
                    1550,
                    "onliner-2",
                ),
            ]
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=(
                [
                    make_offer(
                        "5 элемент",
                        self.canonical,
                        1490,
                        "five",
                    )
                ],
                True,
                [],
            )
        )
        service._search_twenty_one_vek_by_query = AsyncMock(
            return_value=[
                make_offer(
                    "21vek",
                    self.canonical,
                    1450,
                    "twenty-one",
                ),
                make_offer(
                    "21vek",
                    "Apple iPhone 17 Pro 256GB",
                    100,
                    "rejected",
                ),
            ]
        )
        service._search_shop_by_query = AsyncMock(return_value=[])
        service._search_electrosila_query = AsyncMock(return_value=[])
        service._search_zeon_query = AsyncMock(return_value=[])
        return service

    async def test_ingests_all_accepted_offers_only(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report.return_value = Mock(
            total_offers=4,
            created_products=1,
            merged_offers=3,
            updated_offers=0,
            product_keys=("product-1",),
        )
        service = self.build_service(catalog_service)

        result = await service.search_all_sources_by_onliner_key("bosch")

        catalog_service.ingest_offers_with_report.assert_called_once()
        ingested = list(
            catalog_service.ingest_offers_with_report.call_args.args[0]
        )
        self.assertEqual(len(ingested), 4)
        self.assertEqual(
            {offer.url for offer in ingested},
            {
                "https://example.com/onliner-1",
                "https://example.com/onliner-2",
                "https://example.com/five",
                "https://example.com/twenty-one",
            },
        )
        self.assertNotIn(
            "https://example.com/rejected",
            {offer.url for offer in ingested},
        )
        self.assertEqual(
            [offer.source for offer in result.offers],
            ["21vek", "5 элемент", "Onliner"],
        )

    async def test_catalog_failure_does_not_break_search(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report.side_effect = RuntimeError(
            "catalog unavailable"
        )
        service = self.build_service(catalog_service)

        with self.assertLogs(
            "app.services.price_service",
            level="ERROR",
        ) as captured:
            result = await service.search_all_sources_by_onliner_key(
                "bosch"
            )

        self.assertEqual(len(result.offers), 3)
        self.assertTrue(
            any(
                "Master catalog shadow ingest failed" in message
                for message in captured.output
            )
        )


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    patch_price_service()
    write_integration_tests()
