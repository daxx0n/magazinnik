import unittest

from app.sources.electrosila import ElectrosilaSource
from app.sources.five_element import FiveElementSource
from app.sources.onliner import OnlinerSource
from app.sources.twenty_one_vek import TwentyOneVekSource
from app.sources.zeon import ZeonSource


class SourceParsingMatrixTest(unittest.TestCase):
    def test_onliner_keeps_titles_and_model_keys(self) -> None:
        source = OnlinerSource()
        cases = [
            (
                "Apple iPhone 17 Pro 256GB (глубокий синий)",
                "ip17pro256db",
                "mobile/apple/ip17pro256db",
            ),
            (
                "Bosch Serie 4 HBA534EB3",
                "hba534eb3",
                "oven_cooker/bosch/hba534eb3",
            ),
            (
                "Телевизор LG OLED55C4RLA",
                "oled55c4rla",
                "tv/lg/oled55c4rla",
            ),
        ]

        for title, key, path in cases:
            with self.subTest(title=title):
                candidate = source._parse_candidate(
                    {
                        "full_name": title,
                        "key": key,
                        "html_url": f"https://catalog.onliner.by/{path}",
                    }
                )
                self.assertIsNotNone(candidate)
                assert candidate is not None
                self.assertEqual(candidate.key, key)
                self.assertEqual(candidate.title, title)

    def test_five_element_keeps_search_titles_for_matching(self) -> None:
        cases = [
            (
                "355063",
                "Смартфон Apple iPhone 17 Pro 256GB "
                "Deep Blue (MG8J4KH/A)",
            ),
            (
                "867107",
                "Духовой шкаф BOSCH HBA534EB3",
            ),
            (
                "console-2116",
                "Игровая приставка Sony PlayStation 5 Slim "
                "(CFI-2116A)",
            ),
        ]

        for product_id, title in cases:
            with self.subTest(title=title):
                candidate = FiveElementSource._parse_candidate(
                    {
                        "id": product_id,
                        "name": title,
                        "link_url": f"/products/{product_id}-item",
                    }
                )
                self.assertIsNotNone(candidate)
                assert candidate is not None
                self.assertEqual(candidate.title, title)
                self.assertEqual(candidate.key, product_id)

    def test_twenty_one_vek_keeps_available_model_offers(self) -> None:
        source = TwentyOneVekSource()
        cases = [
            (
                "Смартфон Apple iPhone 17 Pro 256GB (темно-синий)",
                "/mobile/iphone17pro256gb_apple_10019149.html",
            ),
            (
                "Холодильник с морозильником LG GC-B509SECL",
                "/refrigerators/gcb509secl_lg.html",
            ),
            (
                "Посудомоечная машина Bosch SMS4HMI07E",
                "/dishwashers/sms4hmi07e_bosch.html",
            ),
        ]

        for title, link in cases:
            with self.subTest(title=title):
                offer = source._offer_from_search_result(
                    {
                        "status": "in",
                        "name": title,
                        "link": link,
                        "salePrice": "4599.00",
                    }
                )
                self.assertIsNotNone(offer)
                assert offer is not None
                self.assertEqual(offer.title, title)
                self.assertEqual(offer.price, 4599.0)

    def test_electrosila_keeps_titles_and_prices(self) -> None:
        source = ElectrosilaSource()
        cases = [
            (
                "Смартфон APPLE iPhone 17 Pro 12GB/256GB "
                "MG8J4KH/A (Deep Blue)",
                "4 899 . 00 р",
            ),
            ("Духовой шкаф BOSCH HBA534EB3", "1 599 . 90 р"),
            ("Телевизор SAMSUNG UE43U8000FUXRU", "1 299 . 00 р"),
        ]

        for index, (title, price) in enumerate(cases):
            with self.subTest(title=title):
                html = f"""
                <div class="tov_prew_search">
                  <a href="https://sila.by/catalog/category/item-{index}">
                    <img alt="{title}">
                  </a>
                  <div class="btn_zak">В КОРЗИНУ!</div>
                  <div class="price">{price}</div>
                </div>
                """
                offers = source._parse_search_results(html, limit=1)

                self.assertEqual(len(offers), 1)
                self.assertEqual(offers[0].title, title)
                self.assertGreater(offers[0].price, 0)

    def test_zeon_keeps_titles_and_club_prices(self) -> None:
        source = ZeonSource()
        cases = [
            (
                "Телефон Apple iPhone 17 Pro 256GB "
                "(глубокий синий)",
                "3 584,30",
            ),
            (
                "Электрический духовой шкаф Bosch "
                "Serie 4 HBA534EB3",
                "1 197,70",
            ),
            ("Телевизор Samsung UE43U8000FUXRU", "1 054,00"),
        ]

        for index, (title, price) in enumerate(cases):
            with self.subTest(title=title):
                html = f"""
                <div class="catalog-item">
                  <div class="catalog-item-title">
                    <a href="https://www.zeon.by/product/item-{index}/">
                      {title}
                    </a>
                  </div>
                  <span class="catalog-item-stock instock">В наличии</span>
                  <div class="catalog-item-pricemini">{price} руб*</div>
                </div>
                """
                offers = source._parse_page(
                    html,
                    "https://www.zeon.by/search/?q=model",
                    limit=1,
                )

                self.assertEqual(len(offers), 1)
                self.assertEqual(offers[0].title, title)
                self.assertGreater(offers[0].price, 0)


if __name__ == "__main__":
    unittest.main()
