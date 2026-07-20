import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.handlers import search
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import ComparisonResult
from app.services.search_load import SearchRequestCoordinator


def comparison() -> ComparisonResult:
    return ComparisonResult(
        offers=[
            ProductOffer(
                source="Onliner",
                title="Google Pixel 8 8GB/128GB (Obsidian)",
                price=2_000.0,
                currency="BYN",
                available=True,
                url="https://example.com/pixel8",
            )
        ],
        source_statuses=[],
        match_decisions=[],
        query="internal",
        product_title="Google Pixel 8 8GB/128GB (Obsidian)",
        product_key="pixel8",
    )


class HandlerLoadTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        search.comparison_diagnostics.clear()
        search.product_searches.clear()
        search.product_search_parents.clear()

    async def test_fifty_users_selecting_same_product_share_one_comparison(
        self,
    ) -> None:
        result = comparison()
        calls = 0

        async def loader(
            product_key: str,
            original_query: str | None = None,
        ) -> ComparisonResult:
            nonlocal calls
            calls += 1
            self.assertEqual(product_key, "pixel8")
            self.assertIsNone(original_query)
            await asyncio.sleep(0.02)
            return result

        service = Mock()
        service.search_all_sources_by_onliner_key = AsyncMock(
            side_effect=loader
        )
        history = Mock()
        renderer = AsyncMock()
        coordinator = SearchRequestCoordinator[
            tuple[str, str],
            ComparisonResult,
        ](max_concurrent=4, max_pending=100)

        messages = []
        for index in range(50):
            message = AsyncMock()
            message.chat.id = 10_000 + index
            messages.append(message)

        with (
            patch.object(search, "price_service", service),
            patch.object(search, "comparison_coordinator", coordinator),
            patch.object(
                search,
                "get_price_history_repository",
                return_value=history,
            ),
            patch.object(search, "show_comparison", renderer),
        ):
            await asyncio.gather(
                *(
                    search.load_product_comparison(
                        message,
                        "pixel8",
                        original_query=f"Pixel request {index}",
                        user_id=index,
                    )
                    for index, message in enumerate(messages)
                )
            )

        self.assertEqual(calls, 1)
        self.assertEqual(renderer.await_count, 50)
        self.assertEqual(history.record_offers.call_count, 1)
        self.assertEqual(len(search.comparison_diagnostics), 50)
        for index in range(50):
            stored = search.comparison_diagnostics[(10_000 + index, index)]
            self.assertEqual(stored.query, f"Pixel request {index}")

    def test_foreign_user_cannot_open_or_delete_callback_session(self) -> None:
        product = ProductCandidate(
            key="pixel8",
            title="Google Pixel 8",
            url="https://example.com/pixel8",
        )
        session_id = search.store_product_search(
            [product],
            query="Pixel",
            owner_chat_id=100,
            owner_user_id=200,
        )
        foreign_callback = Mock()
        foreign_callback.message.chat.id = 100
        foreign_callback.from_user.id = 201

        self.assertIsNone(
            search.authorized_product_search(
                foreign_callback,
                session_id,
            )
        )
        self.assertIn(session_id, search.product_searches)

        owner_callback = Mock()
        owner_callback.message.chat.id = 100
        owner_callback.from_user.id = 200
        self.assertEqual(
            search.authorized_product_search(owner_callback, session_id),
            [product],
        )

    def test_owner_callback_refreshes_lru_session(self) -> None:
        product = ProductCandidate(
            key="pixel8",
            title="Google Pixel 8",
            url="https://example.com/pixel8",
        )
        session_id = search.store_product_search(
            [product],
            query="Pixel",
            owner_chat_id=100,
            owner_user_id=200,
        )
        callback = Mock()
        callback.message.chat.id = 100
        callback.from_user.id = 200

        self.assertEqual(
            search.authorized_product_search(callback, session_id),
            [product],
        )
        self.assertEqual(next(reversed(search.product_searches)), session_id)


if __name__ == "__main__":
    unittest.main()
