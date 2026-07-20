import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.models.catalog import ExternalCatalogItem, ProductIdentity
from app.models.product import ProductCandidate
from app.models.search_result import ComparisonResult
from app.services.catalog_first_search import CatalogFirstPriceService
from app.services.catalog_service import CatalogService
from app.services.price_service import PriceService
from app.sources import ProductNotFoundError


class CatalogFirstSearchTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def catalog_service(
        *,
        updated_at: datetime,
        title: str = "Bosch HBA534EB3",
    ) -> CatalogService:
        service = CatalogService()
        service.catalog.upsert(
            ExternalCatalogItem(
                source="Onliner",
                external_id="bosch-onliner",
                title=title,
                url="https://catalog.onliner.by/oven/bosch/hba534eb3",
                price=1499.0,
                currency="BYN",
                available=True,
                identity=ProductIdentity(
                    brand="bosch",
                    model="hba534eb3",
                ),
                updated_at=updated_at,
            )
        )
        service.catalog.upsert(
            ExternalCatalogItem(
                source="21vek",
                external_id="bosch-21vek",
                title="Духовой шкаф Bosch HBA 534 EB3",
                url="https://21vek.by/ovens/hba534eb3_bosch.html",
                price=1450.0,
                currency="BYN",
                available=True,
                identity=ProductIdentity(
                    brand="bosch",
                    model="hba534eb3",
                ),
                updated_at=updated_at,
            )
        )
        return service

    async def test_disabled_flag_uses_onliner_search(self) -> None:
        service = CatalogFirstPriceService(
            catalog_service=self.catalog_service(
                updated_at=datetime.now(timezone.utc)
            ),
            catalog_search_enabled=False,
        )
        expected = ProductCandidate(
            key="onliner-bosch",
            title="Bosch HBA534EB3",
            url="https://catalog.onliner.by/oven/bosch/hba534eb3",
        )
        service._onliner_source.find_products = AsyncMock(
            return_value=[expected]
        )

        products = await service.find_onliner_products("Bosch HBA534EB3")

        self.assertEqual(products, [expected])
        service._onliner_source.find_products.assert_awaited_once()

    async def test_fresh_catalog_hit_avoids_live_search(self) -> None:
        service = CatalogFirstPriceService(
            catalog_service=self.catalog_service(
                updated_at=datetime.now(timezone.utc)
            ),
            catalog_search_enabled=True,
            freshness_hours=24,
        )
        service._onliner_source.find_products = AsyncMock(
            side_effect=AssertionError("live search must not run")
        )

        products = await service.find_onliner_products("Bosch HBA534EB3")
        result = await service.search_all_sources_by_onliner_key(
            products[0].key
        )

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].key, "catalog:product-1")
        self.assertEqual(result.product_key, "catalog:product-1")
        self.assertEqual(result.master_product_key, "product-1")
        self.assertTrue(result.catalog_presentation)
        self.assertEqual(
            [offer.source for offer in result.offers],
            ["21vek", "Onliner"],
        )
        self.assertEqual(result.offers[0].price, 1450.0)
        service._onliner_source.find_products.assert_not_awaited()

    async def test_stale_catalog_hit_refreshes_through_live_search(self) -> None:
        catalog_service = self.catalog_service(
            updated_at=datetime.now(timezone.utc) - timedelta(hours=48)
        )
        service = CatalogFirstPriceService(
            catalog_service=catalog_service,
            catalog_search_enabled=True,
            freshness_hours=24,
        )
        live_candidate = ProductCandidate(
            key="onliner-bosch",
            title="Bosch HBA534EB3",
            url="https://catalog.onliner.by/oven/bosch/hba534eb3",
        )
        service._onliner_source.find_products = AsyncMock(
            return_value=[live_candidate]
        )
        live_result = ComparisonResult(
            offers=[],
            source_statuses=[],
            match_decisions=[],
            query="Bosch HBA534EB3",
            product_title="Bosch HBA534EB3",
            product_key=live_candidate.key,
        )

        products = await service.find_onliner_products("Bosch HBA534EB3")
        with patch.object(
            PriceService,
            "search_all_sources_by_onliner_key",
            new=AsyncMock(return_value=live_result),
        ) as live_search:
            result = await service.search_all_sources_by_onliner_key(
                products[0].key
            )

        live_search.assert_awaited_once_with(
            live_candidate.key,
            original_query="Bosch HBA534EB3",
        )
        self.assertEqual(result.product_key, "catalog:product-1")
        self.assertEqual(result.master_product_key, "product-1")
        self.assertEqual(result.master_product_title, "Bosch HBA534EB3")
        self.assertTrue(result.catalog_presentation)

    async def test_live_failure_returns_stored_stale_offers(self) -> None:
        service = CatalogFirstPriceService(
            catalog_service=self.catalog_service(
                updated_at=datetime.now(timezone.utc) - timedelta(hours=48)
            ),
            catalog_search_enabled=True,
            freshness_hours=24,
        )
        service._onliner_source.find_products = AsyncMock(
            side_effect=RuntimeError("Onliner unavailable")
        )

        products = await service.find_onliner_products("Bosch HBA534EB3")
        with self.assertLogs(
            "app.services.catalog_first_search",
            level="ERROR",
        ):
            result = await service.search_all_sources_by_onliner_key(
                products[0].key
            )

        self.assertEqual(len(result.offers), 2)
        self.assertEqual(result.product_key, "catalog:product-1")
        self.assertTrue(result.catalog_presentation)

    async def test_missing_master_product_is_reported(self) -> None:
        service = CatalogFirstPriceService(
            catalog_service=CatalogService(),
            catalog_search_enabled=True,
        )

        with self.assertRaises(ProductNotFoundError):
            await service.search_all_sources_by_onliner_key(
                "catalog:missing"
            )


if __name__ == "__main__":
    unittest.main()
