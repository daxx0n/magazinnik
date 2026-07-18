import unittest

from app.sources.five_element import FiveElementSource
from app.sources.onliner import OnlinerSource
from app.sources.twenty_one_vek import TwentyOneVekSource


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


if __name__ == "__main__":
    unittest.main()
