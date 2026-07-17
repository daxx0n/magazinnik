import unittest

from app.services.price_service import PriceService


class ModelMatchingTest(unittest.TestCase):
    def test_explains_mismatch_reason(self) -> None:
        cases = [
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
                "Apple MacBook Air M3",
                "Apple MacBook Air M2",
                "model_number",
            ),
            (
                "Apple iPhone 16 Pro",
                "Apple iPhone 16 Pro Max",
                "version",
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
                "Духовой шкаф HBA-534-EB3",
                "Духовой шкаф HBA534EB3",
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
                "Apple MacBook Air M3",
                "Ноутбук Apple MacBook Air 13 M3",
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


if __name__ == "__main__":
    unittest.main()
