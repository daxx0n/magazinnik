import asyncio
import unittest

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import ComparisonResult, SourceSearchStatus
from app.services.any_color import (
    aggregate_any_color_results,
    load_any_color_results,
)


def offer(source: str, seller: str, url: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        seller=seller,
        title=f"Phone {seller}",
        price=price,
        currency="BYN",
        available=True,
        url=url,
    )


def comparison(
    key: str,
    offers: list[ProductOffer],
    statuses: list[SourceSearchStatus],
) -> ComparisonResult:
    return ComparisonResult(
        offers=offers,
        source_statuses=statuses,
        match_decisions=[],
        query=key,
        product_title=key,
        product_key=key,
        duration_seconds=0.5,
    )


class AnyColorTest(unittest.IsolatedAsyncioTestCase):
    async def test_limits_parallel_color_comparisons(self) -> None:
        products = [
            ProductCandidate(
                key=f"color-{index}",
                title=f"Phone 256GB Color {index}",
                url=f"https://example.com/{index}",
            )
            for index in range(12)
        ]
        active = 0
        peak = 0

        async def loader(product: ProductCandidate) -> ComparisonResult:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.005)
            active -= 1
            return comparison(product.key, [], [])

        results = await load_any_color_results(
            products,
            loader,
            max_concurrent=3,
        )

        self.assertEqual(len(results), 12)
        self.assertLessEqual(peak, 3)

    async def test_partial_loader_failure_does_not_cancel_other_colors(self) -> None:
        products = [
            ProductCandidate(
                key="black",
                title="Phone 256GB Black",
                url="https://example.com/black",
            ),
            ProductCandidate(
                key="blue",
                title="Phone 256GB Blue",
                url="https://example.com/blue",
            ),
        ]

        async def loader(product: ProductCandidate) -> ComparisonResult:
            if product.key == "black":
                raise RuntimeError("temporary failure")
            return comparison(
                product.key,
                [offer("Shop.by", "Seller", "https://shop/item", 1000)],
                [],
            )

        results = await load_any_color_results(products, loader)
        self.assertEqual([result.product_key for result in results], ["blue"])

    def test_aggregates_cheapest_offers_and_source_statuses(self) -> None:
        black = comparison(
            "black",
            [
                offer("Shop.by", "Seller", "https://shop/item/", 1200),
                offer("Onliner", "Store A", "https://onliner/a", 1300),
            ],
            [
                SourceSearchStatus(
                    source="Shop.by",
                    state="found",
                    matched_offers=1,
                    checked_candidates=5,
                ),
                SourceSearchStatus(source="21vek", state="not_found"),
            ],
        )
        blue = comparison(
            "blue",
            [
                offer("Shop.by", "Seller", "https://shop/item", 1100),
                offer("21vek", "Store B", "https://21vek/b", 1250),
            ],
            [
                SourceSearchStatus(
                    source="Shop.by",
                    state="found",
                    matched_offers=1,
                    checked_candidates=4,
                ),
                SourceSearchStatus(
                    source="21vek",
                    state="found",
                    matched_offers=1,
                ),
            ],
        )

        result = aggregate_any_color_results(
            [black, blue],
            original_query="Phone",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual([item.price for item in result.offers], [1100, 1250, 1300])
        self.assertEqual(result.product_key, "blue")
        self.assertEqual(result.query, "Phone")
        statuses = {status.source: status for status in result.source_statuses}
        self.assertEqual(statuses["21vek"].state, "found")
        self.assertEqual(statuses["Shop.by"].matched_offers, 2)
        self.assertEqual(statuses["Shop.by"].checked_candidates, 9)

    def test_returns_none_when_no_color_has_offers(self) -> None:
        result = aggregate_any_color_results(
            [comparison("black", [], []), comparison("blue", [], [])]
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
