import unittest

from app.services.product_identity import ProductIdentityBuilder


class ProductIdentityBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = ProductIdentityBuilder()

    def test_builds_phone_identity_from_title(self) -> None:
        identity = self.builder.build(
            "Смартфон Apple iPhone 15 Pro 256GB (черный титан)"
        )

        self.assertEqual(identity.brand, "apple")
        self.assertEqual(identity.model, "iphone 15 pro")
        self.assertEqual(identity.memory, "256GB")
        self.assertEqual(identity.color, "black_titanium")

    def test_normalizes_explicit_identifiers(self) -> None:
        identity = self.builder.build(
            "Apple iPhone 15 Pro",
            ean=" 019-5949-042157 ",
            mpn=" MT-QV3 ",
        )

        self.assertEqual(identity.ean, "0195949042157")
        self.assertEqual(identity.mpn, "mtqv3")

    def test_prefers_explicit_brand_and_model(self) -> None:
        identity = self.builder.build(
            "Игровая консоль Sony PlayStation 5 Slim",
            brand="Sony",
            model="PlayStation 5 Slim",
        )

        self.assertEqual(identity.brand, "sony")
        self.assertEqual(identity.model, "playstation 5 slim")

    def test_extracts_playstation_revision(self) -> None:
        identity = self.builder.build(
            "Sony PlayStation 5 Slim CFI-2016A"
        )

        self.assertEqual(identity.revision, "cfi-2016a")

    def test_extracts_named_revision(self) -> None:
        identity = self.builder.build(
            "Робот-пылесос Xiaomi S10 rev. 2"
        )

        self.assertEqual(identity.revision, "2")

    def test_removes_generic_product_prefix(self) -> None:
        identity = self.builder.build(
            "Телевизор Samsung QE55S90DAUXRU"
        )

        self.assertEqual(identity.brand, "samsung")
        self.assertEqual(identity.model, "qe55s90dauxru")

    def test_returns_partial_identity_for_sparse_title(self) -> None:
        identity = self.builder.build("Пылесос")

        self.assertIsNone(identity.brand)
        self.assertIsNone(identity.model)
        self.assertIsNone(identity.memory)
        self.assertIsNone(identity.color)


if __name__ == "__main__":
    unittest.main()
