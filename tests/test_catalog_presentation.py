import unittest
from unittest.mock import AsyncMock

from app.handlers.search import (
    format_comparison_diagnostics,
    show_comparison,
)
from app.models.offer import ProductOffer
from app.models.search_result import ComparisonResult


def offer(source: str, title: str, price: float) -> ProductOffer:
    return ProductOffer(
        source=source,
        title=title,
        price=price,
        currency="BYN",
        available=True,
        url=f"https://example.com/{source}",
    )


class CatalogPresentationTest(unittest.IsolatedAsyncioTestCase):
    async def test_grouped_comparison_shows_one_master_title(self) -> None:
        message = AsyncMock()
        offers = [
            offer("21vek", "Духовой шкаф Bosch HBA 534 EB3", 1400),
            offer("Onliner", "Bosch HBA534EB3", 1500),
        ]

        await show_comparison(
            message=message,
            offers=offers,
            product_title="Bosch HBA534EB3",
            grouped=True,
        )

        text = message.edit_text.call_args.args[0]
        self.assertEqual(text.count("🏷️"), 1)
        self.assertIn("🏷️ Bosch HBA534EB3", text)
        self.assertIn("21vek", text)
        self.assertIn("Onliner", text)
        self.assertIn(
            "Предложения объединены в одну карточку",
            text,
        )
        self.assertNotIn(
            "Убедись, что ссылки ведут",
            text,
        )

    async def test_legacy_comparison_keeps_offer_titles(self) -> None:
        message = AsyncMock()
        offers = [
            offer("21vek", "Bosch HBA 534 EB3", 1400),
            offer("Onliner", "Bosch HBA534EB3", 1500),
        ]

        await show_comparison(message=message, offers=offers)

        text = message.edit_text.call_args.args[0]
        self.assertEqual(text.count("🏷️"), 2)
        self.assertIn("Убедись, что ссылки ведут", text)

    def test_diagnostics_exposes_master_product(self) -> None:
        comparison = ComparisonResult(
            offers=[offer("Onliner", "Bosch HBA534EB3", 1500)],
            source_statuses=[],
            match_decisions=[],
            product_title="Духовой шкаф Bosch HBA534EB3",
            master_product_key="product-7",
            master_product_title="Bosch HBA534EB3",
            catalog_presentation=True,
        )

        text = format_comparison_diagnostics(comparison)

        self.assertIn("🏷️ Bosch HBA534EB3", text)
        self.assertIn("🧩 Мастер-карточка: product-7", text)


if __name__ == "__main__":
    unittest.main()
