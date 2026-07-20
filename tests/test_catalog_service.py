import unittest

from app.models.offer import ProductOffer
from app.services.catalog_service import CatalogService


class CatalogServiceTest(unittest.TestCase):
    def test_ingests_offers_into_master_catalog(self) -> None:
        service = CatalogService()

        first = ProductOffer(
            source="Onliner",
            title="Apple iPhone 15 Pro 256GB Black Titanium",
            url="https://example.com/iphone",
            price=1000,
            currency="BYN",
            available=True,
        )

        second = ProductOffer(
            source="21vek",
            title="Apple iPhone 15 Pro 256 GB Black Titanium",
            url="https://example.com/iphone-2",
            price=950,
            currency="BYN",
            available=True,
        )

        products = service.ingest_offers((first, second))

        self.assertEqual(len(products), 2)
        self.assertEqual(len(service.catalog.products), 1)
        self.assertEqual(len(service.catalog.products[0].offers), 2)

    def test_searches_master_catalog(self) -> None:
        service = CatalogService()
        service.ingest_offer(
            ProductOffer(
                source="Onliner",
                title="Samsung Galaxy S25 Ultra 256GB",
                url="https://example.com/samsung",
                price=1200,
                currency="BYN",
                available=True,
            )
        )

        result = service.search("Galaxy S25")

        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
