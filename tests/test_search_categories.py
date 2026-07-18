import unittest
from unittest.mock import AsyncMock, patch

from app.handlers.search import (
    handle_search,
    product_search_parents,
    product_searches,
)
from app.models.category import ProductCategory
from app.models.product import ProductCandidate


class SearchCategoriesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        product_searches.clear()
        product_search_parents.clear()

    @patch("app.handlers.search.price_service")
    async def test_brand_query_stops_for_category_selection(
        self,
        service,
    ) -> None:
        message = AsyncMock()
        message.text = "Samsung"
        status_message = AsyncMock()
        message.answer.return_value = status_message
        service.should_categorize_query.return_value = True
        service.find_onliner_categories = AsyncMock(
            return_value=[
                ProductCategory("mobile", "Телефоны и смартфоны"),
                ProductCategory("tv", "Телевизоры"),
            ]
        )
        service.find_onliner_products = AsyncMock()

        await handle_search(message)

        service.find_onliner_products.assert_not_awaited()
        text = status_message.edit_text.await_args.args[0]
        keyboard = status_message.edit_text.await_args.kwargs[
            "reply_markup"
        ]
        self.assertIn("нескольким категориям", text)
        self.assertEqual(
            [row[0].text for row in keyboard.inline_keyboard],
            ["Телефоны и смартфоны", "Телевизоры"],
        )

    @patch("app.handlers.search.price_service")
    async def test_single_category_keeps_direct_model_flow(
        self,
        service,
    ) -> None:
        message = AsyncMock()
        message.text = "iPhone"
        status_message = AsyncMock()
        message.answer.return_value = status_message
        service.should_categorize_query.return_value = True
        service.find_onliner_categories = AsyncMock(
            return_value=[
                ProductCategory("mobile", "Телефоны и смартфоны")
            ]
        )
        service.find_onliner_products = AsyncMock(
            return_value=[
                ProductCandidate(
                    key="iphone17",
                    title="Apple iPhone 17 256GB",
                    url=(
                        "https://catalog.onliner.by/mobile/"
                        "apple/iphone17"
                    ),
                )
            ]
        )

        await handle_search(message)

        service.find_onliner_products.assert_awaited_once_with(
            "iPhone",
            category="mobile",
        )
        text = status_message.edit_text.await_args.args[0]
        self.assertIn("Выбери точную модель", text)


if __name__ == "__main__":
    unittest.main()
