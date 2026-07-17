import unittest
from unittest.mock import AsyncMock

from app.models.offer import ProductOffer
from app.models.search_result import SourceSearchStatus
from app.handlers.search import format_source_status
from app.services.price_service import PriceService


def make_offer(
    source: str,
    title: str,
    price: float,
) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url="https://example.com/product",
    )


class SourceStatusesTest(unittest.IsolatedAsyncioTestCase):
    async def test_reports_every_checked_source(self) -> None:
        service = PriceService()
        canonical = "Духовой шкаф Bosch HBA534EB3"

        service.search_onliner_key = AsyncMock(
            return_value=[
                make_offer("Onliner", canonical, 1500),
                make_offer("Onliner", canonical, 1550),
            ]
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=([], True)
        )
        service._twenty_one_vek_source.find_offers = AsyncMock(
            return_value=[]
        )

        result = (
            await service.search_all_sources_by_onliner_key(
                "bosch-hba534eb3"
            )
        )

        self.assertEqual(
            [status.source for status in result.source_statuses],
            ["Onliner", "5 элемент", "21vek"],
        )
        self.assertEqual(
            [status.state for status in result.source_statuses],
            ["found", "filtered", "not_found"],
        )

    def test_formats_all_status_variants(self) -> None:
        cases = [
            (
                SourceSearchStatus("Onliner", "found", 5),
                "✅ Onliner — точных предложений: 5",
            ),
            (
                SourceSearchStatus("5 элемент", "filtered"),
                "⚠️ 5 элемент — варианты найдены, но не "
                "совпали с выбранной моделью",
            ),
            (
                SourceSearchStatus("21vek", "not_found"),
                "➖ 21vek — точная модель не найдена",
            ),
            (
                SourceSearchStatus("21vek", "unavailable"),
                "❌ 21vek — временно недоступен",
            ),
        ]

        for status, expected in cases:
            with self.subTest(state=status.state):
                self.assertEqual(
                    format_source_status(status),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
