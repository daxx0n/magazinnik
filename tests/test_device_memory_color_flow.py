import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.handlers import search
from app.models.offer import ProductOffer
from app.models.product import ProductCandidate
from app.models.search_result import ComparisonResult
from app.services.model_selection import group_model_variants
from app.services.selection_flow import ordered_variant_groups


def candidate(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(key=key, title=title, url=f"https://example.com/{key}")


def result(key: str, title: str, price: float) -> ComparisonResult:
    return ComparisonResult(
        offers=[
            ProductOffer(
                source="Onliner",
                title=title,
                price=price,
                currency="BYN",
                available=True,
                url=f"https://example.com/offer/{key}",
                seller="shop",
            )
        ],
        source_statuses=[],
        match_decisions=[],
        query="iPhone 17",
        product_title=title,
        product_key=key,
    )


class DeviceMemoryColorFlowTest(unittest.IsolatedAsyncioTestCase):
    def test_device_buttons_always_open_memory_step(self) -> None:
        products = [candidate("single", "Apple iPhone 17 256GB Black")]
        keyboard = search.build_product_keyboard(products, "session", 0)

        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data,
            "olg:session:0",
        )

    async def test_color_keyboard_starts_with_any_option(self) -> None:
        products = [
            candidate("black", "Apple iPhone 17 256GB Black"),
            candidate("blue", "Apple iPhone 17 256GB Blue"),
        ]
        group = ordered_variant_groups(products, group_model_variants)[0]
        message = AsyncMock()

        await search.show_color_selection(
            message=message,
            group=group,
            products=products,
            back_callback="back",
            any_callback="ola:session:0:0",
        )

        markup = message.edit_text.await_args.kwargs["reply_markup"]
        self.assertEqual(
            markup.inline_keyboard[0][0].callback_data,
            "ola:session:0:0",
        )
        self.assertIn("Любой", markup.inline_keyboard[0][0].text)

    async def test_any_color_returns_offers_sorted_by_price(self) -> None:
        products = [
            candidate("black", "Apple iPhone 17 256GB Black"),
            candidate("blue", "Apple iPhone 17 256GB Blue"),
            candidate("white", "Apple iPhone 17 256GB White"),
        ]
        service = Mock()
        service.search_all_sources_by_onliner_key = AsyncMock(
            side_effect=[
                result("black", products[0].title, 3200),
                result("blue", products[1].title, 2900),
                result("white", products[2].title, 3100),
            ]
        )
        message = AsyncMock()
        history = Mock()
        renderer = AsyncMock()

        with (
            patch.object(search, "price_service", service),
            patch.object(search, "get_price_history_repository", return_value=history),
            patch.object(search, "show_comparison", renderer),
        ):
            await search.load_any_color_comparison(
                message=message,
                products=products,
                original_query="iPhone 17",
                user_id=10,
            )

        rendered_offers = renderer.await_args.kwargs["offers"]
        self.assertEqual([offer.price for offer in rendered_offers], [2900, 3100, 3200])
        self.assertEqual(renderer.await_args.kwargs["product_key"], "blue")


if __name__ == "__main__":
    unittest.main()
