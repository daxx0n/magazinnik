import unittest

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.services.model_selection import group_model_variants
from app.services.price_sanity import (
    filter_price_outliers,
    is_plausible_full_price,
)
from app.services.product_identity import ProductIdentityBuilder
from app.services.master_catalog import MasterCatalog
from app.services.catalog_adapter import CatalogOfferAdapter


def offer(title: str, price: float, seller: str) -> ProductOffer:
    return ProductOffer(
        source=seller,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.test/{seller}/{price}",
        seller=seller,
    )


class UniversalCatalogRegressionTest(unittest.TestCase):
    def test_samsung_washer_titles_have_one_identity(self) -> None:
        builder = ProductIdentityBuilder()

        identities = {
            builder.build(title)
            for title in (
                "Стиральная машина Samsung WW90T554CAT/LP",
                "Samsung WW90T554CAT",
                "Samsung Стиральная машина Samsung WW90T554CAT/LP",
            )
        }

        self.assertEqual(len(identities), 1)
        identity = identities.pop()
        self.assertEqual(identity.brand, "samsung")
        self.assertEqual(identity.model, "ww90t554cat")

    def test_region_suffixes_do_not_create_duplicate_cards(self) -> None:
        products = [
            ProductCandidate(str(index), title, f"https://example.test/{index}")
            for index, title in enumerate(
                (
                    "Стиральная машина Samsung WW90T554CAT/LP",
                    "Samsung WW90T554CAT/S7",
                    "Samsung WW90T554CAT",
                )
            )
        ]

        groups = group_model_variants(products)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].products), 3)

    def test_master_catalog_merges_washer_region_codes(self) -> None:
        catalog = MasterCatalog()
        adapter = CatalogOfferAdapter()

        for index, title in enumerate(
            (
                "Стиральная машина Samsung WW90T554CAT/LP",
                "Samsung WW90T554CAT/S7",
                "Samsung WW90T554CAT",
            )
        ):
            catalog.upsert(adapter.from_offer(offer(title, 1700 + index, str(index))))

        self.assertEqual(len(catalog.products), 1)
        self.assertEqual(catalog.offer_count, 3)

    def test_payment_fragment_is_not_a_washer_price(self) -> None:
        title = "Стиральная машина Samsung WW90T554CAT/LP"

        self.assertFalse(is_plausible_full_price(title, 25, "BYN"))
        self.assertTrue(is_plausible_full_price(title, 1799, "BYN"))

    def test_installment_label_is_rejected_for_any_category(self) -> None:
        self.assertFalse(
            is_plausible_full_price(
                "Пылесос Dyson V15",
                55,
                "BYN",
                context="Платёж в месяц 55 BYN",
            )
        )

    def test_cross_source_outlier_is_removed_without_category_rule(self) -> None:
        offers = [
            offer("Фотоаппарат Fujifilm X100VI", 25, "feed-a"),
            offer("Фотоаппарат Fujifilm X100VI", 5200, "feed-b"),
            offer("Фотоаппарат Fujifilm X100VI", 5400, "feed-c"),
        ]

        filtered = filter_price_outliers(offers)

        self.assertEqual([item.price for item in filtered], [5200, 5400])

    def test_legitimate_cheap_accessory_is_kept(self) -> None:
        self.assertTrue(
            is_plausible_full_price("Кабель USB-C Samsung", 25, "BYN")
        )


if __name__ == "__main__":
    unittest.main()
