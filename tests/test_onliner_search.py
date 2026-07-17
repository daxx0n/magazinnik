import unittest
from unittest.mock import AsyncMock

from app.sources.onliner import OnlinerSource


class FakeClient:
    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def raw_product(key: str, title: str) -> dict[str, str]:
    return {
        "key": key,
        "full_name": title,
        "html_url": (
            "https://catalog.onliner.by/mobile/apple/"
            f"{key}"
        ),
    }


class OnlinerSearchTest(unittest.IsolatedAsyncioTestCase):
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
                {"products": []},
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
            3,
        )
        self.assertEqual(
            source._request_json.await_args_list[1].kwargs[
                "params"
            ]["page"],
            "2",
        )


if __name__ == "__main__":
    unittest.main()
