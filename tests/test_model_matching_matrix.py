import unittest

from app.services.price_service import PriceService


class ModelMatchingMatrixTest(unittest.TestCase):
    def test_accepts_equivalent_titles_across_brands_and_categories(
        self,
    ) -> None:
        cases = [
            (
                "5 элемент",
                "Bosch Serie 4 HBA534EB3",
                "Электрический духовой шкаф Bosch HBA-534-EB3",
                "Bosch HBA534EB3",
            ),
            (
                "5 элемент",
                "DeLonghi Magnifica S ECAM 22.110.B",
                "Кофемашина DeLonghi Magnifica S ECAM22.110.B",
                "DeLonghi ECAM 22.110.B",
            ),
            (
                "Shop.by",
                "DeLonghi Magnifica S ECAM 22.110.B",
                "Кофемашина DeLonghi MAGNIFICA S ECAM 22.110 B",
                "DeLonghi ECAM 22.110.B",
            ),
            (
                "21vek",
                "Sony PlayStation 5 Slim CFI-21XX "
                "(2 ревизия, с дисководом)",
                "Игровая приставка Sony PlayStation 5 Slim / "
                "CFI-2116 A01Y",
                "Sony PlayStation 5 Slim",
            ),
            (
                "Shop.by",
                "Samsung Galaxy S24 Ultra SM-S928B 256GB",
                "Смартфон Samsung Galaxy S24 Ultra "
                "SM-S928BZKDEUC 12GB/256GB",
                "Samsung SM-S928B 256GB",
            ),
            (
                "5 элемент",
                "Apple iPhone 17 Pro 256GB (глубокий синий)",
                "Смартфон Apple iPhone 17 Pro 256GB "
                "Deep Blue (MG8J4KH/A)",
                "iPhone 17 Pro 256GB",
            ),
            (
                "21vek",
                "Google Pixel 9 Pro 256GB (Obsidian)",
                "Смартфон Google Pixel 9 Pro 12GB/256GB Obsidian",
                "Google Pixel 9 Pro 256GB",
            ),
            (
                "5 элемент",
                "Samsung Crystal UHD DU7100 UE55DU7100UXRU",
                "Телевизор Samsung UE55DU7100UXRU 55 дюймов",
                "Samsung UE55DU7100UXRU",
            ),
            (
                "21vek",
                "LG OLED C4 OLED55C4RLA",
                "Телевизор LG OLED55C4RLA OLED evo",
                "LG OLED55C4RLA",
            ),
            (
                "Shop.by",
                "Xiaomi 14T Pro 512GB (черный)",
                "Смартфон Xiaomi 14T Pro 12GB/512GB Black",
                "Xiaomi 14T Pro 512GB",
            ),
            (
                "21vek",
                "Apple MacBook Air 13 M3 2024 256GB",
                "Ноутбук Apple MacBook Air 13.6 M3 8/256GB 2024",
                "MacBook Air M3 256GB",
            ),
            (
                "Shop.by",
                "Huawei Pura 70 Pro 512GB (черный)",
                "Смартфон Huawei Pura 70 Pro 12GB/512GB Black",
                "Huawei Pura 70 Pro 512GB",
            ),
            (
                "5 элемент",
                "ASUS TUF Gaming A15 FA507NV",
                "Ноутбук Asus TUF Gaming A15 FA507NV-LP031",
                "ASUS FA507NV",
            ),
            (
                "21vek",
                "Lenovo LOQ 15IRX9 83DV00PBRK",
                "Ноутбук Lenovo LOQ 15IRX9 / 83DV00PBRK",
                "Lenovo 83DV00PBRK",
            ),
            (
                "Shop.by",
                "Roborock Q8 Max (черный)",
                "Робот-пылесос Roborock Q8 Max Black",
                "Roborock Q8 Max",
            ),
            (
                "5 элемент",
                "Dyson V15 Detect Absolute",
                "Пылесос Dyson V15 Detect Absolute",
                "Dyson V15 Detect",
            ),
            (
                "5 элемент",
                "Apple AirPods Pro 2",
                "Наушники Apple AirPods Pro 2 (MTJV3HN/A) с USB-C",
                "AirPods Pro 2",
            ),
            (
                "21vek",
                "Sony WH-1000XM5 (черный)",
                "Наушники Sony WH1000XM5 Black",
                "Sony WH-1000XM5",
            ),
            (
                "Shop.by",
                "JBL Flip 6 (черный)",
                "Портативная колонка JBL FLIP6 Black",
                "JBL Flip 6",
            ),
            (
                "21vek",
                "Nintendo Switch OLED (белый)",
                "Игровая приставка Nintendo Switch OLED White",
                "Nintendo Switch OLED",
            ),
            (
                "Shop.by",
                "Microsoft Xbox Series X 1TB",
                "Игровая приставка Microsoft Xbox Series X 1 TB",
                "Xbox Series X",
            ),
            (
                "5 элемент",
                "Bosch Serie 4 SMS4HMI07E",
                "Посудомоечная машина Bosch SMS4HMI07E",
                "Bosch SMS4HMI07E",
            ),
            (
                "21vek",
                "LG GC-B509SECL",
                "Холодильник с морозильником LG GC-B509SECL",
                "LG GC-B509SECL",
            ),
            (
                "Shop.by",
                "Samsung WW90T554CAT",
                "Стиральная машина Samsung WW90T554CAT/LP",
                "Samsung WW90T554CAT",
            ),
            (
                "21vek",
                "Электрическая зубная щетка Oral-B iO 6",
                "Зубная щетка Oral-B iO6",
                "Oral-B iO 6",
            ),
            (
                "Shop.by",
                "Портативная колонка JBL Charge 5",
                "JBL Charge 5",
                "JBL Charge 5",
            ),
            (
                "5 элемент",
                "Стиральная машина Samsung WW90T554CAT",
                "Samsung WW90T554CAT/LP",
                "Samsung WW90T554CAT",
            ),
            (
                "Shop.by",
                "Apple MacBook Air 13 M3 2024 256GB",
                "MacBook Air 13 M3 2024 256GB",
                "MacBook Air M3 256GB",
            ),
            (
                "21vek",
                "Microsoft Xbox Series X 1TB",
                "Xbox Series X 1TB",
                "Xbox Series X",
            ),
            (
                "5 элемент",
                "Xiaomi Redmi Note 13 Pro 256GB",
                "Redmi Note 13 Pro 8GB/256GB",
                "Redmi Note 13 Pro 256GB",
            ),
            (
                "Shop.by",
                "Google Pixel 9 Pro 256GB",
                "Pixel 9 Pro 12GB/256GB",
                "Pixel 9 Pro 256GB",
            ),
            (
                "21vek",
                "Холодильник с морозильником Атлант ХМ 4624-101",
                "Холодильник Атлант ХМ-4624-101",
                "Атлант ХМ 4624-101",
            ),
        ]

        for source, canonical, candidate, requested in cases:
            with self.subTest(source=source, candidate=candidate):
                self.assertIsNone(
                    PriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                        requested_title=requested,
                    )
                )

    def test_rejects_nearby_models_and_other_modifications(self) -> None:
        cases = [
            ("Bosch HBA534EB3", "Bosch HBA514BS3"),
            ("Samsung UE55DU7100UXRU", "Samsung UE50DU7100UXRU"),
            ("LG OLED55C4RLA", "LG OLED55C5RLA"),
            ("Apple iPhone 17 Pro 256GB", "iPhone 17 Pro Max 256GB"),
            ("Google Pixel 9 Pro 256GB", "Google Pixel 9 Pro XL 256GB"),
            ("Apple iPhone 17 Pro 256GB", "iPhone 17 Pro 512GB"),
            (
                "Apple iPhone 17 Pro 256GB Deep Blue",
                "Apple iPhone 17 Pro 256GB Silver",
            ),
            ("Xiaomi 14T Pro 512GB", "Xiaomi 14T 512GB"),
            ("Huawei Pura 70 Pro", "Huawei Pura 70 Ultra"),
            ("ASUS FA507NV", "ASUS FA507NU"),
            ("Lenovo 83DV00PBRK", "Lenovo 83DV00QARK"),
            ("Roborock Q8 Max", "Roborock Q8 Max+"),
            ("Dyson V15 Detect", "Dyson V12 Detect"),
            ("Sony WH-1000XM5", "Sony WH-1000XM4"),
            ("JBL Flip 6", "JBL Flip 5"),
            ("Nintendo Switch OLED", "Nintendo Switch Lite"),
            ("Microsoft Xbox Series X", "Microsoft Xbox Series S"),
            (
                "Sony PlayStation 5 Slim CFI-21XX",
                "Sony PlayStation 5 Slim CFI-2000A01",
            ),
            (
                "Sony PlayStation 5 Slim CFI-21XX "
                "(2 ревизия, с дисководом)",
                "Sony PlayStation 5 Slim Digital Edition "
                "CFI-2116B (без дисковода)",
            ),
            (
                "Apple MacBook Air 13 M3 2024 256GB",
                "Apple MacBook Air 13 M3 2023 256GB",
            ),
            (
                "Samsung Galaxy Tab S10 256GB Wi-Fi",
                "Samsung Galaxy Tab S10 256GB 5G",
            ),
            (
                "Apple Watch Series 10 GPS 46mm",
                "Apple Watch Series 10 GPS + Cellular 46mm",
            ),
            (
                "Apple AirPods Pro 2",
                "Чехол для Apple AirPods Pro 2",
            ),
            (
                "Apple AirPods Pro 2",
                "Амбушюры Apple AirPods Pro 1, Pro 2, Pro 3",
            ),
            (
                "Apple AirPods Pro 2",
                "Aмбушюры Apple AirPods Pro 1, Pro 2, Pro 3 "
                "(Xs, S, L) белый",
            ),
            (
                "Apple iPhone 17 Pro 256GB",
                "Apple iPhone 17 Pro 256GB Refurbished",
            ),
            (
                "Sony PlayStation 5 Slim",
                "Sony PlayStation 5 Slim + DualSense",
            ),
            (
                "Microsoft Xbox Series X 1TB",
                "Microsoft Xbox Series X Digital Edition 1TB",
            ),
            (
                "Apple AirPods Pro 2 (с разъемом Lightning)",
                "Apple AirPods Pro 2 (с разъемом USB Type-C)",
            ),
            (
                "Roborock Q8 Max (с русской озвучкой, белый)",
                "Roborock Q8 Max (с английской озвучкой, белый)",
            ),
        ]

        for canonical, candidate in cases:
            with self.subTest(candidate=candidate):
                self.assertIsNotNone(
                    PriceService._model_mismatch_reason(
                        canonical,
                        candidate,
                    )
                )


if __name__ == "__main__":
    unittest.main()
