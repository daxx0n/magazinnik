import unittest

from app.services.price_service import PriceService


class ModelMatchingTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
