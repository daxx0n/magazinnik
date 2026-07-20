import unittest

from app.models.offer import ProductOffer
from app.services.catalog_service import CatalogService


class CatalogLookupTest(unittest.TestCase):
    def test_returns_product_by_stable_key(self) -> None:
        service = CatalogService()
        product = service.ingest_offer(
            ProductOffer(
                source="Onliner",
                title="Bosch HBA534EB3",
                price=1500,
                currency="BYN",
                available=True,
                url="https://example.com/bosch",
            )
        )

        self.assertIs(service.get_product(product.key), product)
        self.assertIsNone(service.get_product("missing"))


if __name__ == "__main__":
    unittest.main()
