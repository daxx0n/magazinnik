import unittest
from unittest.mock import AsyncMock

from app.sources.zeon import ZeonSource


def search_card(
    title: str,
    regular_price: str,
    path: str,
    *,
    club_price: str | None = None,
    stock_class: str = "instock",
    delivery: str = "Доставка 25.07.2026",
) -> str:
    club_price_html = (
        f'<div class="catalog-item-pricemini">'
        f"{club_price} руб*</div>"
        if club_price is not None
        else ""
    )
    return f"""
    <div class="catalog-item">
      <div class="catalog-item-title">
        <a href="https://www.zeon.by/product/{path}/">{title}</a>
      </div>
      <span class="catalog-item-stock {stock_class}">
        {delivery}
      </span>
      <div class="catalog-item-price">{regular_price} руб</div>
      {club_price_html}
    </div>
    """


def product_page(
    title: str,
    price: str,
    *,
    availability: str = "InStock",
) -> str:
    return f"""
    <main>
      <h1 itemprop="name">{title}</h1>
      <div itemprop="offers">
        <link itemprop="availability"
              href="http://schema.org/{availability}">
        <meta itemprop="price" content="{price}">
      </div>
      <div id="delivery-tab-1">
        <p>Ориентировочная поставка:
          <strong class="color-green">25.07.2026 (сб)</strong>
        </p>
      </div>
      <div>С клубной картой</div>
    </main>
    """


class ZeonSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_club_price_and_sorts_offers(self) -> None:
        source = ZeonSource()
        source._download_search_page = AsyncMock(
            return_value=(
                search_card(
                    "Телефон Apple iPhone 17 Pro 256GB "
                    "(глубокий синий)",
                    "3 871,00",
                    "1840902-iphone-17-pro-blue",
                    club_price="3 584,30",
                )
                + search_card(
                    "Электрический духовой шкаф Bosch "
                    "Serie 4 HBA534EB3",
                    "1 293,50",
                    "1779258-bosch-hba534eb3",
                    club_price="1 197,70",
                ),
                "https://www.zeon.by/search/?q=model",
            )
        )

        offers = await source.find_offers("Model", limit=10)

        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0].price, 1197.7)
        self.assertEqual(offers[0].seller, "Zeon")
        self.assertEqual(
            offers[0].availability_text,
            "В наличии; цена с клубной картой",
        )
        self.assertEqual(
            offers[1].delivery_text,
            "Доставка 25.07.2026",
        )

    async def test_parses_direct_product_redirect(self) -> None:
        source = ZeonSource()
        url = (
            "https://www.zeon.by/product/"
            "1779258-bosch-serie-4-hba534eb3/"
        )
        title = (
            "Электрический духовой шкаф "
            "Bosch Serie 4 HBA534EB3"
        )
        source._download_search_page = AsyncMock(
            return_value=(
                product_page(title, "1197.70"),
                url,
            )
        )

        offers = await source.find_offers("Bosch HBA534EB3")

        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].title, title)
        self.assertEqual(offers[0].price, 1197.7)
        self.assertEqual(offers[0].url, url)
        self.assertEqual(
            offers[0].delivery_text,
            "25.07.2026 (сб)",
        )

    async def test_ignores_unavailable_and_unsafe_cards(self) -> None:
        source = ZeonSource()
        html = (
            search_card(
                "Нет в продаже",
                "999,00",
                "unavailable",
                stock_class="outofstock",
            )
            + search_card(
                "Подменённая ссылка",
                "1,00",
                "unsafe",
            ).replace(
                "https://www.zeon.by/product/unsafe/",
                "https://example.com/product/unsafe/",
            )
        )
        source._download_search_page = AsyncMock(
            return_value=(
                html,
                "https://www.zeon.by/search/?q=test",
            )
        )

        offers = await source.find_offers("Телефон")

        self.assertEqual(offers, [])

    async def test_ignores_short_query(self) -> None:
        source = ZeonSource()
        source._download_search_page = AsyncMock()

        offers = await source.find_offers("a")

        self.assertEqual(offers, [])
        source._download_search_page.assert_not_awaited()

    def test_extracts_only_expected_security_cookie(self) -> None:
        source = ZeonSource()
        html = (
            '<title>Verification</title><script>'
            '(function(){let c="hg-security=token_123-ABC=; '
            'path=/; max-age=120";document.cookie=c})()'
            "</script>"
        )

        self.assertTrue(source._is_verification_page(html))
        self.assertEqual(
            source._security_cookie_from_html(html),
            ("hg-security", "token_123-ABC="),
        )
        self.assertIsNone(
            source._security_cookie_from_html(
                'let c="other-cookie=value; path=/"'
            )
        )


if __name__ == "__main__":
    unittest.main()
