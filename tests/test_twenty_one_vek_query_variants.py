import unittest
from unittest.mock import AsyncMock

from app.models.offer import ProductOffer
from app.sources.twenty_one_vek import TwentyOneVekSource


CANONICAL = "LG NANO 4K UHD AI NU90 43NU900B6LA"
EXACT_TITLE = 'Телевизор LG 43" 43NU900B6LA'
WRONG_TITLE = 'Телевизор LG 50" 50NU900B6LA'


def offer(title: str, price: float) -> ProductOffer:
    return ProductOffer(
        source="21vek",
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://www.21vek.by/{price}",
        seller="21vek",
    )


class TwentyOneVekQueryVariantTest(unittest.TestCase):
    def test_compact_tv_query_keeps_brand_family_and_full_code(self) -> None:
        variants = TwentyOneVekSource._query_variants(CANONICAL)

        self.assertEqual(variants[0], "LG NU90 43NU900B6LA")
        self.assertIn("LG 43NU900B6LA", variants)
        self.assertEqual(variants[-1], CANONICAL)

    def test_compact_queries_are_generic_across_product_families(self) -> None:
        cases = (
            (
                "Samsung Galaxy A55 SM-A556B 8GB/256GB",
                "Samsung A55 SM-A556B",
            ),
            (
                "Huawei nova Y63 GFY-LX1 6GB/128GB",
                "Huawei Y63 GFY-LX1",
            ),
            ("Bosch Serie 4 HBA534EB3", "Bosch HBA534EB3"),
            ("TCL QLED TV 55C745 4K", "TCL 55C745"),
        )
        for query, expected_first in cases:
            with self.subTest(query=query):
                self.assertEqual(
                    TwentyOneVekSource._query_variants(query)[0],
                    expected_first,
                )

    def test_measurements_are_not_added_as_model_identity(self) -> None:
        variants = TwentyOneVekSource._query_variants(
            "LG NU90 43NU900B6LA 4K 120Hz 33W 8GB/256GB"
        )
        compact = variants[0].casefold()

        self.assertNotIn("4k", compact)
        self.assertNotIn("120hz", compact)
        self.assertNotIn("33w", compact)
        self.assertNotIn("8gb", compact)
        self.assertNotIn("256gb", compact)


class TwentyOneVekExactCodePriorityTest(unittest.IsolatedAsyncioTestCase):
    async def test_exact_full_code_is_returned_before_broad_results(self) -> None:
        source = TwentyOneVekSource()
        source._find_offers_once = AsyncMock(
            return_value=[
                offer(EXACT_TITLE, 1290.0),
                offer(WRONG_TITLE, 1690.0),
            ]
        )

        result = await source.find_offers(CANONICAL, limit=5)

        self.assertEqual([item.title for item in result], [EXACT_TITLE])
        source._find_offers_once.assert_awaited_once_with(
            "LG NU90 43NU900B6LA",
            limit=20,
        )

    async def test_original_query_remains_fallback_when_code_is_omitted(self) -> None:
        source = TwentyOneVekSource()
        omitted_code = offer("Смартфон Samsung Galaxy A55 8GB/256GB", 1200.0)

        async def find_once(query: str, limit: int) -> list[ProductOffer]:
            if query == "Samsung A55 SM-A556B":
                return [omitted_code]
            if query == "Samsung SM-A556B":
                return []
            return [omitted_code]

        source._find_offers_once = AsyncMock(side_effect=find_once)

        result = await source.find_offers(
            "Samsung Galaxy A55 SM-A556B 8GB/256GB",
            limit=5,
        )

        self.assertEqual([item.title for item in result], [omitted_code.title])
        self.assertEqual(
            [call.args[0] for call in source._find_offers_once.await_args_list],
            [
                "Samsung A55 SM-A556B",
                "Samsung SM-A556B",
                "Samsung Galaxy A55 SM-A556B 8GB/256GB",
            ],
        )


if __name__ == "__main__":
    unittest.main()
