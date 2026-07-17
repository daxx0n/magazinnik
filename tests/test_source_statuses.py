import unittest
from unittest.mock import AsyncMock

from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import SourceSearchStatus
from app.handlers.search import (
    build_product_keyboard,
    format_product_page_text,
    format_source_status,
)
from app.services.price_service import PriceService
from app.sources import ProductNotFoundError


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
    def test_keeps_only_cheapest_offer_per_source(self) -> None:
        offers = [
            make_offer("Onliner", "Model", 1200),
            make_offer("Onliner", "Model", 1100),
            make_offer("5 элемент", "Model", 1300),
            make_offer("21vek", "Model", 1250),
        ]

        result = PriceService._prepare_aggregate_offers(
            offers
        )

        self.assertEqual(
            [(offer.source, offer.price) for offer in result],
            [
                ("Onliner", 1100),
                ("21vek", 1250),
                ("5 элемент", 1300),
            ],
        )

    def test_paginates_product_variants(self) -> None:
        products = [
            ProductCandidate(
                key=f"model-{index}",
                title=f"Model {index}",
                url=f"https://example.com/{index}",
            )
            for index in range(23)
        ]

        keyboard = build_product_keyboard(
            products=products,
            search_id="search",
            page=1,
        )
        rows = keyboard.inline_keyboard

        self.assertEqual(len(rows), 11)
        self.assertEqual(
            rows[0][0].callback_data,
            "ol:model-10",
        )
        self.assertEqual(
            rows[9][0].callback_data,
            "ol:model-19",
        )
        self.assertEqual(
            [button.text for button in rows[-1]],
            [
                "⏮ В начало",
                "⬅️ Назад",
                "Далее ➡️",
            ],
        )
        self.assertEqual(
            format_product_page_text(23, 1),
            "Нашёл вариантов: 23.\n"
            "Страница 2 из 3.\n\n"
            "Выбери точную модель:",
        )

    async def test_continues_when_onliner_has_no_offers(self) -> None:
        service = PriceService()
        canonical = "LG OLED C4 OLED55C4RLA"
        service._onliner_candidates["oled55c4rla"] = (
            ProductCandidate(
                key="oled55c4rla",
                title=canonical,
                url="https://example.com/onliner",
            )
        )
        service.search_onliner_key = AsyncMock(
            side_effect=ProductNotFoundError(
                "Нет продавцов"
            )
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=(
                [make_offer("5 элемент", canonical, 3000)],
                True,
                [],
            )
        )
        service._twenty_one_vek_source.find_offers = AsyncMock(
            return_value=[]
        )

        result = (
            await service.search_all_sources_by_onliner_key(
                "oled55c4rla"
            )
        )

        self.assertEqual(len(result.offers), 1)
        self.assertEqual(result.offers[0].source, "5 элемент")
        self.assertEqual(
            [status.state for status in result.source_statuses],
            ["not_found", "found", "not_found"],
        )

    async def test_reports_every_checked_source(self) -> None:
        service = PriceService()
        canonical = "Духовой шкаф Bosch HBA534EB3"

        service.search_onliner_key = AsyncMock(
            return_value=[
                make_offer("Onliner", canonical, 1500),
                make_offer("Onliner", canonical, 1550),
            ]
        )
        service._onliner_queries["bosch-hba534eb3"] = (
            "Bosch HBA534EB3"
        )
        service._search_five_element_by_query = AsyncMock(
            return_value=([], True, [])
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
        service._search_five_element_by_query.assert_awaited_once_with(
            query="Bosch HBA534EB3",
            canonical_title=canonical,
        )

    def test_formats_all_status_variants(self) -> None:
        cases = [
            (
                SourceSearchStatus("Onliner", "found", 5),
                "✅ Onliner — предложение найдено",
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
