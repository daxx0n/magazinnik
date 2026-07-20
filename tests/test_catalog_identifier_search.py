import unittest

from app.models.catalog import (
    ExternalCatalogItem,
    MasterCatalogProduct,
    ProductIdentity,
)
from app.services.catalog_service import CatalogService
from app.services.master_catalog import MasterCatalog


class CatalogIdentifierSearchTest(unittest.TestCase):
    @staticmethod
    def product(
        *,
        key: str,
        title: str,
        brand: str,
        model: str,
        ean: str | None = None,
        mpn: str | None = None,
        offer_title: str | None = None,
        offer_identity: ProductIdentity | None = None,
    ) -> MasterCatalogProduct:
        identity = ProductIdentity(
            brand=brand,
            model=model,
            ean=ean,
            mpn=mpn,
        )
        return MasterCatalogProduct(
            key=key,
            title=title,
            identity=identity,
            offers=[
                ExternalCatalogItem(
                    source="Shop",
                    external_id=f"{key}-offer",
                    title=offer_title or title,
                    url=f"https://example.com/{key}",
                    identity=offer_identity or identity,
                )
            ],
        )

    def service(self) -> CatalogService:
        catalog = MasterCatalog()
        catalog.restore(
            [
                self.product(
                    key="pixel-8",
                    title="Google Pixel 8 8GB/128GB",
                    brand="google",
                    model="pixel 8",
                    ean="0840244706081",
                    mpn="GA04834-US",
                ),
                self.product(
                    key="bosch-oven",
                    title="Духовой шкаф Bosch HBA534EB3",
                    brand="bosch",
                    model="HBA534EB3",
                    mpn="HBA534EB3",
                    offer_title="Bosch HBA-534-EB3 духовой шкаф",
                ),
                self.product(
                    key="pixel-case",
                    title="Чехол с маркировкой GA04834US",
                    brand="generic",
                    model="pixel case",
                ),
                self.product(
                    key="offer-identifier",
                    title="Наушники Sony",
                    brand="sony",
                    model="WH-1000XM5",
                    offer_identity=ProductIdentity(
                        brand="sony",
                        model="WH-1000XM5",
                        ean="4548736132580",
                        mpn="YY2954",
                    ),
                ),
            ]
        )
        return CatalogService(catalog=catalog)

    def test_finds_by_exact_ean(self) -> None:
        results = self.service().search("0840244706081")
        self.assertEqual([product.key for product in results], ["pixel-8"])

    def test_finds_by_mpn_with_different_separators(self) -> None:
        results = self.service().search("GA 04834 US")
        self.assertEqual(results[0].key, "pixel-8")
        self.assertNotIn("pixel-case", [product.key for product in results[:1]])

    def test_finds_normalized_model_without_separators(self) -> None:
        results = self.service().search("HBA-534-EB3")
        self.assertEqual(results[0].key, "bosch-oven")

    def test_finds_identifier_from_external_offer_identity(self) -> None:
        by_ean = self.service().search("4548736132580")
        by_mpn = self.service().search("YY-2954")

        self.assertEqual(by_ean[0].key, "offer-identifier")
        self.assertEqual(by_mpn[0].key, "offer-identifier")

    def test_keeps_title_and_brand_model_search(self) -> None:
        service = self.service()

        self.assertEqual(service.search("Google Pixel 8")[0].key, "pixel-8")
        self.assertEqual(service.search("духовой Bosch")[0].key, "bosch-oven")

    def test_empty_query_returns_no_results(self) -> None:
        self.assertEqual(self.service().search("   "), [])


if __name__ == "__main__":
    unittest.main()
