import unittest
from unittest.mock import AsyncMock

from app.sources.electrosila import ElectrosilaSource


def offer_card(
    title: str,
    price: str,
    path: str,
    *,
    buy_text: str = "В КОРЗИНУ!",
    availability: str = "Остался 1 товар!",
    delivery: str = "завтра",
    old_price: str | None = None,
) -> str:
    old_price_html = (
        f"<s><b>{old_price}</b></s>"
        if old_price is not None
        else ""
    )
    return f"""
    <div class="tov_prew_search">
      <a href="https://sila.by/catalog/{path}">
        <img alt="{title}">
        <span><b>товар</b><strong>{title}</strong></span>
      </a>
      <div class="btn_zak">{buy_text}</div>
      <div class="price">
        <div><b>{price}</b>{old_price_html}</div>
      </div>
      <div class="action"><div class="act">{availability}</div></div>
      <div class="nal_box">
        <div class="deliv_inner deliv_reys">
          Доставка: <span>{delivery}</span>
        </div>
      </div>
    </div>
    """


class ElectrosilaSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_sorts_and_deduplicates_offers(self) -> None:
        source = ElectrosilaSource()
        source._download_search_pages = AsyncMock(
            return_value=[
                offer_card(
                    "Смартфон APPLE iPhone 17 Pro 12GB/256GB "
                    "MG8J4KH/A (Deep Blue)",
                    "4 899 . 00 р",
                    "mobilnye_telefony/APPLE/iphone_17_pro_blue",
                ),
                offer_card(
                    "Духовой шкаф BOSCH HBA534EB3",
                    "1 599 . 90 р",
                    "duhovye_shkafy/BOSCH/hba534eb3",
                    availability="В наличии",
                    delivery="сегодня",
                    old_price="1 999 . 00 р",
                ),
                offer_card(
                    "Смартфон APPLE iPhone 17 Pro 12GB/256GB "
                    "MG8J4KH/A (Deep Blue)",
                    "4 899 . 00 р",
                    "mobilnye_telefony/APPLE/iphone_17_pro_blue",
                ),
            ]
        )

        offers = await source.find_offers(
            "Apple iPhone 17 Pro 256GB",
            limit=10,
        )

        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0].price, 1599.9)
        self.assertEqual(offers[0].seller, "Электросила")
        self.assertEqual(offers[0].availability_text, "В наличии")
        self.assertEqual(offers[0].delivery_text, "сегодня")
        self.assertEqual(
            offers[1].url,
            "https://sila.by/catalog/mobilnye_telefony/"
            "APPLE/iphone_17_pro_blue",
        )

    async def test_ignores_unavailable_and_unsafe_cards(self) -> None:
        source = ElectrosilaSource()
        html = (
            offer_card(
                "Нет в продаже",
                "999 . 00 р",
                "phones/unavailable",
                buy_text="НЕТ В НАЛИЧИИ",
            )
            + offer_card(
                "Подменённая ссылка",
                "1 . 00 р",
                "phones/unsafe",
            ).replace(
                "https://sila.by/catalog/phones/unsafe",
                "https://example.com/catalog/phones/unsafe",
            )
        )
        source._download_search_pages = AsyncMock(
            return_value=[html]
        )

        offers = await source.find_offers("Телефон", limit=10)

        self.assertEqual(offers, [])

    async def test_preserves_titles_across_categories(self) -> None:
        cases = [
            "Телевизор SAMSUNG UE43U8000FUXRU",
            "Холодильник BOSCH KIN86VFE0",
            "Кофемашина DELONGHI ECAM290.61.B",
            "Ноутбук ASUS TUF Gaming A15 FA507NV-LP031",
        ]

        for index, title in enumerate(cases):
            with self.subTest(title=title):
                source = ElectrosilaSource()
                source._download_search_pages = AsyncMock(
                    return_value=[
                        offer_card(
                            title,
                            "1 999 . 00 р",
                            f"category/item-{index}",
                        )
                    ]
                )

                offers = await source.find_offers(title, limit=5)

                self.assertEqual(len(offers), 1)
                self.assertEqual(offers[0].title, title)

    async def test_ignores_short_query(self) -> None:
        source = ElectrosilaSource()
        source._download_search_pages = AsyncMock()

        offers = await source.find_offers("a")

        self.assertEqual(offers, [])
        source._download_search_pages.assert_not_awaited()

    def test_accepts_only_safe_pagination_link(self) -> None:
        from bs4 import BeautifulSoup

        source = ElectrosilaSource()
        valid = BeautifulSoup(
            '<a class="navi_dyn" '
            'href="https://sila.by/search/iphone/page/2">Ещё</a>',
            "html.parser",
        )
        invalid = BeautifulSoup(
            '<a class="navi_dyn" '
            'href="https://example.com/search/iphone/page/2">Ещё</a>',
            "html.parser",
        )

        self.assertEqual(
            source._next_page_url(valid),
            "https://sila.by/search/iphone/page/2",
        )
        self.assertIsNone(source._next_page_url(invalid))


if __name__ == "__main__":
    unittest.main()
