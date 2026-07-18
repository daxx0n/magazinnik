import unittest
from unittest.mock import AsyncMock

from app.sources.shop_by import ShopBySource


def offer_row(
    title: str,
    price: str,
    seller: str,
    target_url: str,
    availability: str = "InStock",
) -> str:
    return f"""
    <div class="ShopItemList__ItemBlockRow">
      <div class="ModelList__InfoModelName">
        <a class="ShopItemList__ItemName"
           href="/item.php?url={target_url}">
          <span class="ModelList__NameBlock">{title}</span>
        </a>
      </div>
      <div class="ModelList__InfoPrice">
        <a itemprop="offers">
          <meta itemprop="price" content="{price}">
          <link itemprop="availability"
                href="http://schema.org/{availability}">
        </a>
        <a class="ShopItemList__ShopLink">{seller}</a>
      </div>
      <img alt="Доставка: Бесплатная, сегодня">
    </div>
    """


class ShopBySourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_sorts_and_deduplicates_offers(self) -> None:
        source = ShopBySource()
        source._download_search_page = AsyncMock(
            return_value=(
                offer_row(
                    "Apple iPhone 17 512GB Black MG6P4",
                    "3335.00",
                    "appstudio.by",
                    "https%3A%2F%2Fappstudio.by%2Fiphone-17",
                )
                + offer_row(
                    "Apple iPhone 17 512GB Black MG6P4",
                    "3060.00",
                    "imagic.by",
                    "https%3A%2F%2Fimagic.by%2Fiphone-17",
                )
                + offer_row(
                    "Apple iPhone 17 512GB Black MG6P4",
                    "3060.00",
                    "imagic.by",
                    "https%3A%2F%2Fimagic.by%2Fiphone-17",
                )
                + offer_row(
                    "Apple iPhone 17 512GB Black MG6P4",
                    "2900.00",
                    "old-stock.by",
                    "https%3A%2F%2Fold-stock.by%2Fiphone-17",
                    availability="OutOfStock",
                )
            )
        )

        offers = await source.find_offers(
            "Apple iPhone 17 512GB Black",
            limit=10,
        )

        self.assertEqual(len(offers), 2)
        self.assertEqual(
            [offer.seller for offer in offers],
            ["imagic.by", "appstudio.by"],
        )
        self.assertEqual(offers[0].price, 3060.0)
        self.assertEqual(
            offers[0].url,
            "https://imagic.by/iphone-17",
        )
        self.assertEqual(
            offers[0].delivery_text,
            "Бесплатная, сегодня",
        )
        source._download_search_page.assert_awaited_once_with(
            "Apple iPhone 17 512GB Black"
        )

    async def test_ignores_short_query(self) -> None:
        source = ShopBySource()
        source._download_search_page = AsyncMock()

        offers = await source.find_offers("a")

        self.assertEqual(offers, [])
        source._download_search_page.assert_not_awaited()

    async def test_preserves_model_titles_across_categories(self) -> None:
        cases = [
            "Ноутбук ASUS TUF Gaming A15 FA507NV-LP031",
            "Телевизор LG OLED55C4RLA",
            "Робот-пылесос Roborock Q8 Max Black",
            "Кофемашина DeLonghi ECAM22.110.B",
        ]

        for index, title in enumerate(cases):
            with self.subTest(title=title):
                source = ShopBySource()
                source._download_search_page = AsyncMock(
                    return_value=offer_row(
                        title,
                        "1999.00",
                        f"seller-{index}.by",
                        f"https%3A%2F%2Fseller.by%2Fitem-{index}",
                    )
                )

                offers = await source.find_offers(title, limit=5)

                self.assertEqual(len(offers), 1)
                self.assertEqual(offers[0].title, title)


if __name__ == "__main__":
    unittest.main()
