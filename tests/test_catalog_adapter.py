import unittest

from app.models.offer import ProductOffer
from app.services.catalog_adapter import CatalogOfferAdapter


class CatalogOfferAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = CatalogOfferAdapter()

    def test_converts_offer_and_builds_identity(self) -> None:
        item = self.adapter.from_offer(
            ProductOffer(
                source="Shop",
                title="Apple iPhone 15 Pro 256GB (черный титан)",
                price=3200.0,
                currency="BYN",
                available=True,
                url="https://shop.example/products/iphone-15-pro",
            )
        )

        self.assertEqual(item.source, "Shop")
        self.assertEqual(item.price, 3200.0)
        self.assertEqual(item.identity.brand, "apple")
        self.assertEqual(item.identity.model, "iphone 15 pro")
        self.assertEqual(item.identity.memory, "256GB")
        self.assertEqual(item.identity.color, "black_titanium")

    def test_external_id_is_stable_for_same_url(self) -> None:
        first = ProductOffer(
            source="Shop",
            title="Old title",
            price=100.0,
            currency="BYN",
            available=True,
            url="https://shop.example/item/42",
        )
        second = ProductOffer(
            source="Shop",
            title="Updated title",
            price=90.0,
            currency="BYN",
            available=True,
            url="https://shop.example/item/42",
        )

        self.assertEqual(
            self.adapter.from_offer(first).external_id,
            self.adapter.from_offer(second).external_id,
        )


if __name__ == "__main__":
    unittest.main()
