import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.models.catalog import MasterCatalogProduct, ProductIdentity
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

    def build_service(
        self,
        catalog_service: Mock,
        *,
        presentation_enabled: bool = False,
    ) -> PriceService:
        service = PriceService(
            catalog_service=catalog_service,
            catalog_presentation_enabled=presentation_enabled,
        )
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

    @staticmethod
    def report(*, product_keys: tuple[str, ...], created: int) -> Mock:
        return Mock(
            total_offers=4,
            created_products=created,
            merged_offers=4 - created,
            updated_offers=0,
            product_keys=product_keys,
        )

    @staticmethod
    def master_product() -> MasterCatalogProduct:
        return MasterCatalogProduct(
            key="product-1",
            title="Bosch HBA534EB3",
            identity=ProductIdentity(
                brand="bosch",
                model="hba534eb3",
            ),
        )

    async def test_ingests_all_accepted_offers_only(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=self.report(
                product_keys=("product-1",),
                created=1,
            )
        )
        service = self.build_service(catalog_service)

        result = await service.search_all_sources_by_onliner_key("bosch")

        catalog_service.ingest_offers_with_report_async.assert_awaited_once()
        ingested = list(
            catalog_service.ingest_offers_with_report_async.await_args.args[0]
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
        self.assertFalse(result.catalog_presentation)
        catalog_service.get_product.assert_not_called()

    async def test_enables_master_presentation_for_one_product(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=self.report(
                product_keys=("product-1",),
                created=1,
            )
        )
        catalog_service.get_product.return_value = self.master_product()
        service = self.build_service(
            catalog_service,
            presentation_enabled=True,
        )

        result = await service.search_all_sources_by_onliner_key("bosch")

        self.assertTrue(result.catalog_presentation)
        self.assertEqual(result.master_product_key, "product-1")
        self.assertEqual(result.master_product_title, "Bosch HBA534EB3")
        catalog_service.get_product.assert_called_once_with("product-1")

    async def test_keeps_legacy_view_for_ambiguous_catalog_result(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=self.report(
                product_keys=("product-1", "product-2"),
                created=2,
            )
        )
        service = self.build_service(
            catalog_service,
            presentation_enabled=True,
        )

        result = await service.search_all_sources_by_onliner_key("bosch")

        self.assertFalse(result.catalog_presentation)
        self.assertEqual(result.master_product_key, "")
        catalog_service.get_product.assert_not_called()

    async def test_catalog_failure_does_not_break_search(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            side_effect=RuntimeError("catalog unavailable")
        )
        service = self.build_service(
            catalog_service,
            presentation_enabled=True,
        )

        with self.assertLogs(
            "app.services.price_service",
            level="ERROR",
        ) as captured:
            result = await service.search_all_sources_by_onliner_key(
                "bosch"
            )

        self.assertEqual(len(result.offers), 3)
        self.assertFalse(result.catalog_presentation)
        self.assertTrue(
            any(
                "Master catalog shadow ingest failed" in message
                for message in captured.output
            )
        )

    async def test_catalog_read_failure_keeps_legacy_view(self) -> None:
        catalog_service = Mock()
        catalog_service.ingest_offers_with_report_async = AsyncMock(
            return_value=self.report(
                product_keys=("product-1",),
                created=1,
            )
        )
        catalog_service.get_product.side_effect = RuntimeError("read failed")
        service = self.build_service(
            catalog_service,
            presentation_enabled=True,
        )

        with self.assertLogs(
            "app.services.price_service",
            level="ERROR",
        ):
            result = await service.search_all_sources_by_onliner_key(
                "bosch"
            )

        self.assertFalse(result.catalog_presentation)
        self.assertEqual(result.master_product_title, "")

    def test_reads_presentation_flag_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"MASTER_CATALOG_PRESENTATION_ENABLED": "true"},
            clear=False,
        ):
            service = PriceService(catalog_service=Mock())

        self.assertTrue(service._catalog_presentation_enabled)


if __name__ == "__main__":
    unittest.main()
