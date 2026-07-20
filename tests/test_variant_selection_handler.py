import unittest
from unittest.mock import AsyncMock, Mock

from app.handlers.search import (
    build_product_keyboard,
    show_color_selection,
)
from app.models.product import ProductCandidate
from app.services.model_selection import group_model_variants


def candidate(key: str, title: str) -> ProductCandidate:
    return ProductCandidate(
        key=key,
        title=title,
        url=f"https://example.com/{key}",
    )


class VariantSelectionHandlerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.products = [
            candidate(
                "pixel8-generic",
                "Google Pixel 8 8GB/128GB",
            ),
            candidate(
                "pixel8-obsidian",
                "Google Pixel 8 8GB/128GB (обсидиан)",
            ),
            candidate(
                "pixel8-mint",
                "Google Pixel 8 8GB/128GB (mint)",
            ),
            candidate(
                "pixel7-snow",
                "Google Pixel 7 8GB/128GB (snow)",
            ),
        ]

    def test_product_keyboard_lists_models_not_color_cards(self) -> None:
        markup = build_product_keyboard(
            products=self.products,
            search_id="search",
            page=0,
        )
        buttons = [
            button
            for row in markup.inline_keyboard
            for button in row
            if (button.callback_data or "").startswith("olg:")
        ]

        self.assertEqual(
            [button.text for button in buttons],
            ["Google Pixel 8", "Google Pixel 7"],
        )

    async def test_pixel_8_screen_lists_colors_and_hides_generic_card(self) -> None:
        group = group_model_variants(self.products)[0]
        message = Mock()
        message.edit_text = AsyncMock()

        await show_color_selection(
            message=message,
            group=group,
            products=group.products,
            back_callback="olp:search:0",
        )

        kwargs = message.edit_text.await_args.kwargs
        markup = kwargs["reply_markup"]
        buttons = [
            button
            for row in markup.inline_keyboard
            for button in row
            if (button.callback_data or "").startswith("ol:")
        ]
        labels = {button.text.casefold() for button in buttons}
        callbacks = {button.callback_data for button in buttons}

        self.assertEqual(labels, {"обсидиан", "mint"})
        self.assertEqual(
            callbacks,
            {"ol:pixel8-obsidian", "ol:pixel8-mint"},
        )
        self.assertNotIn("цвет не указан", labels)

    async def test_same_color_memory_variants_keep_both_choices(self) -> None:
        products = [
            candidate(
                "pixel8-128",
                "Google Pixel 8 8GB/128GB (Obsidian)",
            ),
            candidate(
                "pixel8-256",
                "Google Pixel 8 8GB/256GB (Obsidian)",
            ),
        ]
        group = group_model_variants(products)[0]
        message = Mock()
        message.edit_text = AsyncMock()

        await show_color_selection(
            message=message,
            group=group,
            products=products,
            back_callback="olp:search:0",
        )

        markup = message.edit_text.await_args.kwargs["reply_markup"]
        labels = [
            button.text
            for row in markup.inline_keyboard
            for button in row
            if (button.callback_data or "").startswith("ol:")
        ]
        self.assertEqual(
            labels,
            ["Obsidian · 8GB/128GB", "Obsidian · 8GB/256GB"],
        )


if __name__ == "__main__":
    unittest.main()
