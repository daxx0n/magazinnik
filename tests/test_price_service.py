import unittest

from app.services.price_service import PriceService


class ModelMatchingTest(unittest.TestCase):
    def test_detects_only_broad_catalog_queries(self) -> None:
        cases = [
            ("Samsung", True),
            ("Apple iPhone", True),
            ("Samsung Galaxy S25", False),
            ("Bosch HBA534EB3", False),
        ]

        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(
                    PriceService.should_categorize_query(query),
                    expected,
                )

    def test_builds_query_without_color(self) -> None:
        self.assertEqual(
            PriceService._build_cross_source_query(
                "Apple iPhone 17 512GB (черный)"
            ),
            "Apple iPhone 17 512GB",
        )

    def test_builds_source_queries_with_marketing_color(self) -> None:
        cases = [
            (
                "Apple iPhone 17 512GB (голубой)",
                [
                    "Apple iPhone 17 512GB голубой",
                    "Apple iPhone 17 512GB Mist Blue",
                    "Apple iPhone 17 512GB",
                ],
            ),
            (
                "Apple iPhone 15 Pro 256GB (природный титан)",
                [
                    "Apple iPhone 15 Pro 256GB природный титан",
                    "Apple iPhone 15 Pro 256GB Natural Titanium",
                    "Apple iPhone 15 Pro 256GB",
                ],
            ),
        ]

        for title, expected in cases:
            with self.subTest(title=title):
                query = PriceService._build_cross_source_query(title)
                self.assertEqual(
                    PriceService._build_source_queries(query, title),
                    expected,
                )

    def test_explains_mismatch_reason(self) -> None:
        cases = [
            (
                "Apple AirPods Pro 2",
                "Bingo VT-i11 AirPods Pro 2",
                "brand",
            ),
            (
                "Смартфон Samsung SM-A556E",
                "Чехол для Samsung SM-A556E",
                "accessory",
            ),
            (
                "Духовой шкаф Bosch HBA534EB3",
                "Духовой шкаф Bosch HBA514BS3",
                "model_code",
            ),
            (
                "Apple iPhone 16 Pro 256GB",
                "Apple iPhone 16 Pro 128GB",
                "memory",
            ),
            (
                "Samsung Galaxy A55 8/256GB",
                "Samsung Galaxy A55 12/256GB",
                "memory",
            ),
            (
                "Apple MacBook Air M3",
                "Apple MacBook Air M2",
                "model_number",
            ),
            (
                "Apple iPhone 16 Pro",
                "Apple iPhone 16 Pro Max",
                "version",
            ),
            (
                "DeLonghi ECAM 22.110.B",
                "DeLonghi ECAM 22.114.B",
                "model_code",
            ),
            (
                "Apple iPhone 17 512GB (черный)",
                "Apple iPhone 17 512GB White",
                "color",
            ),
            (
                "Apple iPhone 17 512GB (синий)",
                "Apple iPhone 17 512GB Blue",
                "color",
            ),
            (
                "Blackview BV9300 Pro 12GB/256GB (зеленый)",
                "Blackview BV9300 Pro 12GB/256GB Black",
                "color",
            ),
            (
                "Телефон Samsung 256GB (графитовый)",
                "Телефон Samsung 256GB Black",
                "color",
            ),
            (
                "Телефон Samsung 256GB (голубой)",
                "Телефон Samsung 256GB Blue",
                "color",
            ),
            (
                "Apple iPhone 17 512GB (черный)",
                "Apple iPhone 17 512GB Dual eSIM Black",
                "sim",
            ),
            (
                "Apple iPhone 17 512GB (черный)",
                "Apple iPhone 17 512GB Dual eSIM Black MG6P4",
                "sim",
            ),
            (
                "Apple iPhone 17 Dual SIM 512GB (черный)",
                "Apple iPhone 17 512GB Black",
                "sim",
            ),
        ]

        for canonical, candidate, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(
                    PriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                    ),
                    reason,
                )

    def test_rejects_different_model_codes(self) -> None:
        cases = [
            (
                "Духовой шкаф Bosch Serie 4 HBA534EB3",
                "Духовой шкаф Bosch HBA514BS3",
            ),
            (
                "Телевизор Samsung UE55DU7100UXRU",
                "Телевизор Samsung UE55DU7170UXRU",
            ),
            (
                "Холодильник LG GC-B509SECL",
                "Холодильник LG GC-B459SECL",
            ),
        ]

        for canonical, candidate in cases:
            with self.subTest(canonical=canonical):
                self.assertFalse(
                    PriceService._matches_model(
                        canonical,
                        candidate,
                    )
                )

    def test_accepts_same_model_code(self) -> None:
        cases = [
            (
                "Духовой шкаф Bosch Serie 4 HBA534EB3",
                "Электрический духовой шкаф Bosch HBA534EB3",
            ),
            (
                "Смартфон Samsung SM-A556E",
                "Samsung Galaxy A55 SM-A556E",
            ),
            (
                "Духовой шкаф Bosch HBA-534-EB3",
                "Духовой шкаф Bosch HBA534EB3",
            ),
        ]

        for canonical, candidate in cases:
            with self.subTest(canonical=canonical):
                self.assertTrue(
                    PriceService._matches_model(
                        canonical,
                        candidate,
                    )
                )

    def test_rejects_accessories_for_a_device(self) -> None:
        cases = [
            (
                "Смартфон Samsung SM-A556E",
                "Чехол для Samsung SM-A556E",
            ),
            (
                "Apple AirPods Pro 2",
                "Защитный чехол Apple AirPods Pro 2",
            ),
            (
                "Телевизор LG OLED55C4RLA",
                "Крепление для телевизора LG OLED55C4RLA",
            ),
        ]

        for canonical, candidate in cases:
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    PriceService._matches_model(
                        canonical,
                        candidate,
                    )
                )

    def test_rejects_different_memory_or_version(self) -> None:
        cases = [
            (
                "Apple iPhone 16 Pro 256GB",
                "Apple iPhone 16 Pro 128GB",
            ),
            (
                "Apple iPhone 16 Pro",
                "Apple iPhone 16 Pro Max",
            ),
            (
                "Samsung Galaxy S24 Ultra",
                "Samsung Galaxy S24 Plus",
            ),
            (
                "Apple MacBook Air M3",
                "Apple MacBook Air M2",
            ),
        ]

        for canonical, candidate in cases:
            with self.subTest(canonical=canonical):
                self.assertFalse(
                    PriceService._matches_model(
                        canonical,
                        candidate,
                    )
                )

    def test_accepts_equivalent_general_titles(self) -> None:
        cases = [
            (
                "Apple iPhone 16 Pro 256GB",
                "Смартфон Apple iPhone 16 Pro 256 ГБ",
            ),
            (
                "Samsung Galaxy S24 Ultra",
                "Смартфон Samsung Galaxy S24 Ultra 5G",
            ),
            (
                "Samsung Galaxy S24 256GB (синий)",
                "Samsung Galaxy S24 256GB Blue",
            ),
            (
                "Apple iPhone 17 512GB (синий)",
                "Apple iPhone 17 512GB Mist Blue",
            ),
            (
                "Apple iPhone 17 512GB (фиолетовый)",
                "Apple iPhone 17 512GB Lavender",
            ),
            (
                "Samsung Galaxy A55 8GB/256GB",
                "Samsung Galaxy A55 8/256GB",
            ),
            (
                "Apple MacBook Air M3",
                "Ноутбук Apple MacBook Air 13 M3",
            ),
            (
                "Apple iPhone 17 512GB (черный)",
                "Apple iPhone 17 512GB Black MG6P4",
            ),
        ]

        for canonical, candidate in cases:
            with self.subTest(canonical=canonical):
                self.assertTrue(
                    PriceService._matches_model(
                        canonical,
                        candidate,
                    )
                )

    def test_uses_user_query_for_cross_source_codes(self) -> None:
        cases = [
            (
                "Samsung Galaxy S24 Ultra SM-S928B 256GB",
                "Samsung Galaxy S24 Ultra 12GB/256GB",
                "Samsung Galaxy S24 Ultra 256GB",
                None,
            ),
            (
                "Apple MacBook Air 13 M3 2024 MC8K4",
                "Apple MacBook Air 15 M3 2024 256GB MRYR3",
                "Apple MacBook Air M3 256GB",
                "model_number",
            ),
            (
                "Apple MacBook Air 13 M3 2024 MC8K4",
                "Apple MacBook Air 13 M4 2024 256GB MW0Y3",
                "Apple MacBook Air M3 256GB",
                "model_number",
            ),
            (
                "Xiaomi Redmi Note 13 Pro 4G 8GB/256GB",
                "Xiaomi Redmi Note 15 Pro 8GB/256GB",
                "Xiaomi Redmi Note 13 Pro 256GB",
                "model_number",
            ),
            (
                "DeLonghi Magnifica S ECAM 22.110.B",
                "DeLonghi Magnifica S ECAM22.110.B",
                "DeLonghi ECAM 22.110.B",
                None,
            ),
        ]

        for canonical, candidate, requested, expected in cases:
            with self.subTest(requested=requested):
                self.assertEqual(
                    PriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=requested,
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
