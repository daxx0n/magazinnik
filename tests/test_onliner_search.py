import unittest
from unittest.mock import AsyncMock

from app.sources.onliner import OnlinerSource


class FakeClient:
    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def raw_product(
    key: str,
    title: str,
    category: str = "mobile",
    brand: str = "apple",
) -> dict[str, str]:
    return {
        "key": key,
        "full_name": title,
        "html_url": (
            f"https://catalog.onliner.by/{category}/{brand}/"
            f"{key}"
        ),
    }


def search_page(
    products: list[dict[str, str]],
    current: int,
    last: int,
) -> dict[str, object]:
    return {
        "products": products,
        "page": {
            "current": current,
            "last": last,
        },
    }


class OnlinerSearchTest(unittest.IsolatedAsyncioTestCase):
    async def test_discovers_device_categories_for_brand_query(self) -> None:
        source = OnlinerSource()
        source._create_client = lambda: FakeClient()
        source._request_json = AsyncMock(
            side_effect=[
                search_page(
                    [
                        raw_product(
                            "samsung-phone",
                            "Телефон Samsung Galaxy S25",
                            category="mobile",
                            brand="samsung",
                        ),
                        raw_product(
                            "samsung-case",
                            "Чехол Samsung Galaxy S25",
                            category="phonecase",
                            brand="samsung",
                        ),
                    ],
                    current=1,
                    last=3,
                ),
                search_page(
                    [
                        raw_product(
                            "samsung-buds",
                            "Наушники Samsung Galaxy Buds",
                            category="headphones",
                            brand="samsung",
                        ),
                        raw_product(
                            "samsung-tab",
                            "Планшет Samsung Galaxy Tab",
                            category="tabletpc",
                            brand="samsung",
                        ),
                    ],
                    current=2,
                    last=3,
                ),
                search_page(
                    [
                        raw_product(
                            "samsung-tv",
                            "Телевизор Samsung QLED",
                            category="tv",
                            brand="samsung",
                        ),
                    ],
                    current=3,
                    last=3,
                ),
            ]
        )

        categories = await source.find_categories("Samsung")

        self.assertEqual(
            [(item.key, item.title) for item in categories],
            [
                ("mobile", "Телефоны и смартфоны"),
                ("headphones", "Наушники"),
                ("tabletpc", "Планшеты"),
                ("tv", "Телевизоры"),
            ],
        )
        self.assertEqual(source._request_json.await_count, 3)

    async def test_product_family_query_does_not_become_brand_menu(
        self,
    ) -> None:
        source = OnlinerSource()
        source._create_client = lambda: FakeClient()
        source._request_json = AsyncMock(
            return_value=search_page(
                [
                    raw_product(
                        "iphone17",
                        "Apple iPhone 17",
                        category="mobile",
                    ),
                    raw_product(
                        "earpods",
                        "Apple EarPods for iPhone",
                        category="headphones",
                    ),
                ],
                current=1,
                last=1,
            )
        )

        categories = await source.find_categories("iPhone")

        self.assertEqual(categories, [])

    async def test_loads_only_selected_category(self) -> None:
        source = OnlinerSource()
        source._create_client = lambda: FakeClient()
        source._request_json = AsyncMock(
            side_effect=[
                search_page(
                    [
                        raw_product(
                            "phone",
                            "Телефон Samsung Galaxy S25",
                            category="mobile",
                        )
                    ],
                    current=1,
                    last=4,
                ),
                search_page(
                    [
                        raw_product(
                            "buds-black",
                            "Наушники Samsung Galaxy Buds (черный)",
                            category="headphones",
                        )
                    ],
                    current=2,
                    last=4,
                ),
                search_page(
                    [
                        raw_product(
                            "buds-white",
                            "Наушники Samsung Galaxy Buds (белый)",
                            category="headphones",
                        )
                    ],
                    current=3,
                    last=4,
                ),
                search_page(
                    [
                        raw_product(
                            "tv",
                            "Телевизор Samsung QLED",
                            category="tv",
                        )
                    ],
                    current=4,
                    last=4,
                ),
            ]
        )

        products = await source.find_products(
            "Samsung",
            category="headphones",
        )

        self.assertEqual(
            [product.key for product in products],
            ["buds-black", "buds-white"],
        )
        self.assertEqual(source._request_json.await_count, 4)

    def test_sorts_iphone_generation_and_versions(self) -> None:
        source = OnlinerSource()
        products = [
            source._parse_candidate(
                raw_product(key, title)
            )
            for key, title in [
                ("15", "Apple iPhone 15 128GB (черный)"),
                ("16pro", "Apple iPhone 16 Pro 256GB"),
                ("17pm", "Apple iPhone 17 Pro Max 256GB"),
                ("air", "Apple iPhone Air 256GB"),
                ("17", "Apple iPhone 17 256GB (черный)"),
                ("16", "Apple iPhone 16 128GB"),
                (
                    "17produal",
                    "Apple iPhone 17 Pro Dual SIM 256GB",
                ),
                ("17pro", "Apple iPhone 17 Pro 256GB"),
            ]
        ]
        candidates = [
            product
            for product in products
            if product is not None
        ]

        sorted_products = source._sort_product_family(
            candidates,
            "iPhone",
        )

        self.assertEqual(
            [product.key for product in sorted_products],
            [
                "17",
                "17pro",
                "17produal",
                "17pm",
                "air",
                "16",
                "16pro",
                "15",
            ],
        )

    async def test_loads_all_pages_and_groups_colors(self) -> None:
        source = OnlinerSource()
        source._create_client = lambda: FakeClient()
        source._request_json = AsyncMock(
            side_effect=[
                {
                    "products": [
                        raw_product(
                            "iphone17black",
                            "Apple iPhone 17 256GB (черный)",
                        ),
                        raw_product(
                            "iphone16black",
                            "Apple iPhone 16 256GB (черный)",
                        ),
                        raw_product(
                            "iphone17case",
                            "Чехол для Apple iPhone 17",
                            category="phonecase",
                        ),
                    ]
                },
                {
                    "products": [
                        raw_product(
                            "iphone17purple",
                            "Apple iPhone 17 256GB (сиреневый)",
                        )
                    ]
                },
                {
                    "products": [
                        raw_product(
                            "iphone16case",
                            "Чехол для Apple iPhone 16",
                            category="phonecase",
                        )
                    ]
                },
                {
                    "products": [
                        raw_product(
                            "iphone15glass",
                            "Стекло для Apple iPhone 15",
                            category="protectiveglass",
                        )
                    ]
                },
            ]
        )

        products = await source.find_products("iPhone")

        self.assertEqual(
            [product.key for product in products],
            [
                "iphone17black",
                "iphone17purple",
                "iphone16black",
            ],
        )
        self.assertEqual(
            source._request_json.await_count,
            4,
        )
        self.assertEqual(
            source._request_json.await_args_list[1].kwargs[
                "params"
            ]["page"],
            "2",
        )


if __name__ == "__main__":
    unittest.main()
