import unittest

from app.services.price_service import PriceService


class ModelMatchingTest(unittest.TestCase):
    def test_rejects_a_different_bosch_article(self) -> None:
        self.assertFalse(
            PriceService._matches_model(
                "Духовой шкаф Bosch Serie 4 HBA534EB3",
                "Духовой шкаф Bosch HBA514BS3",
            )
        )

    def test_accepts_the_same_bosch_article(self) -> None:
        self.assertTrue(
            PriceService._matches_model(
                "Духовой шкаф Bosch Serie 4 HBA534EB3",
                "Электрический духовой шкаф Bosch HBA534EB3",
            )
        )


if __name__ == "__main__":
    unittest.main()
