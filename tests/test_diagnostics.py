import unittest
from unittest.mock import AsyncMock, patch

from app.handlers.search import (
    comparison_diagnostics,
    format_comparison_diagnostics,
    handle_diagnostics,
    load_product_comparison,
    store_comparison_diagnostics,
)
from app.models.offer import ProductOffer
from app.models.search_result import (
    ComparisonResult,
    MatchDecision,
    SourceSearchStatus,
)


def comparison_result() -> ComparisonResult:
    offer = ProductOffer(
        source="Onliner",
        title="Apple iPhone 17 512GB (синий)",
        price=3500,
        currency="BYN",
        available=True,
        url="https://example.com/onliner",
        seller="Seller",
    )
    return ComparisonResult(
        offers=[offer],
        source_statuses=[
            SourceSearchStatus(
                source="Onliner",
                state="found",
                matched_offers=1,
                checked_candidates=5,
                duration_seconds=0.42,
            ),
            SourceSearchStatus(
                source="5 элемент",
                state="filtered",
                checked_candidates=7,
                duration_seconds=0.81,
            ),
            SourceSearchStatus(
                source="21vek",
                state="not_found",
                duration_seconds=1.15,
            ),
            SourceSearchStatus(
                source="Shop.by",
                state="unavailable",
                duration_seconds=2.01,
            ),
            SourceSearchStatus(
                source="Электросила",
                state="found",
                matched_offers=1,
                checked_candidates=3,
                duration_seconds=1.21,
            ),
            SourceSearchStatus(
                source="Zeon",
                state="found",
                matched_offers=1,
                checked_candidates=2,
                duration_seconds=1.08,
            ),
        ],
        match_decisions=[
            MatchDecision(
                source="5 элемент",
                title="Apple iPhone 17 256GB Black",
                accepted=False,
                reason="memory",
            ),
            MatchDecision(
                source="5 элемент",
                title="Apple iPhone 17 512GB Blue",
                accepted=False,
                reason="color",
            ),
            MatchDecision(
                source="5 элемент",
                title="Чехол Apple iPhone 17",
                accepted=False,
                reason="accessory",
            ),
        ],
        query="iPhone 17 512GB",
        product_title="Apple iPhone 17 512GB (синий)",
        duration_seconds=2.08,
        completed_at="18.07.2026 14:30:00",
    )


class DiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        comparison_diagnostics.clear()

    def test_formats_compact_diagnostics(self) -> None:
        text = format_comparison_diagnostics(comparison_result())

        self.assertIn("Apple iPhone 17 512GB (Mist Blue)", text)
        self.assertIn("⏱ Общее время: 2.08 с", text)
        self.assertIn("🕒 Завершено: 18.07.2026 14:30:00", text)
        self.assertIn("✅ Onliner — найдено; 0.42 с", text)
        self.assertIn("Проверено: 5; совпало: 1", text)
        self.assertIn("⚠️ 5 элемент — варианты отфильтрованы", text)
        self.assertIn("❌ Shop.by — недоступен", text)
        self.assertIn("✅ Электросила — найдено", text)
        self.assertIn("✅ Zeon — найдено", text)
        self.assertIn("• аксессуар: 1", text)
        self.assertIn("• цвет: 1", text)
        self.assertIn("• память: 1", text)

    async def test_diagnostics_are_isolated_by_chat(self) -> None:
        store_comparison_diagnostics(100, comparison_result())
        own_message = AsyncMock()
        own_message.chat.id = 100
        other_message = AsyncMock()
        other_message.chat.id = 200

        await handle_diagnostics(other_message)
        await handle_diagnostics(own_message)

        self.assertIn(
            "Диагностики пока нет",
            other_message.answer.await_args.args[0],
        )
        self.assertIn(
            "Диагностика последнего сравнения",
            own_message.answer.await_args.args[0],
        )

    async def test_diagnostics_are_isolated_inside_group_chat(self) -> None:
        first = comparison_result()
        second = comparison_result()
        store_comparison_diagnostics(500, first, user_id=1)
        store_comparison_diagnostics(500, second, user_id=2)

        first_message = AsyncMock()
        first_message.chat.id = 500
        first_message.from_user.id = 1
        second_message = AsyncMock()
        second_message.chat.id = 500
        second_message.from_user.id = 2

        await handle_diagnostics(first_message)
        await handle_diagnostics(second_message)

        self.assertIn(
            "Диагностика последнего сравнения",
            first_message.answer.await_args.args[0],
        )
        self.assertIn(
            "Диагностика последнего сравнения",
            second_message.answer.await_args.args[0],
        )
        self.assertIs(comparison_diagnostics[(500, 1)], first)
        self.assertIs(comparison_diagnostics[(500, 2)], second)

    @patch("app.handlers.search.price_service")
    async def test_comparison_stores_diagnostics_before_render(
        self,
        service,
    ) -> None:
        result = comparison_result()
        service.search_all_sources_by_onliner_key = AsyncMock(
            return_value=result
        )
        message = AsyncMock()
        message.chat.id = 300
        message.edit_text.side_effect = [None, RuntimeError("Telegram")]

        with self.assertRaises(RuntimeError):
            await load_product_comparison(
                message,
                "iphone17",
                user_id=42,
            )

        self.assertIs(comparison_diagnostics[(300, 42)], result)


if __name__ == "__main__":
    unittest.main()
