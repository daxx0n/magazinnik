import unittest

from app.services.search_sessions import (
    SearchSessionRegistry,
    SelectionQueryRegistry,
)


class MutableClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class SearchSessionRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()

    def test_session_is_bound_to_chat_and_user(self) -> None:
        registry = SearchSessionRegistry(clock=self.clock)
        registry.register(
            "session",
            query="Pixel",
            owner_chat_id=100,
            owner_user_id=200,
        )

        self.assertIsNotNone(
            registry.authorize("session", chat_id=100, user_id=200)
        )
        self.assertIsNone(
            registry.authorize("session", chat_id=101, user_id=200)
        )
        self.assertIsNone(
            registry.authorize("session", chat_id=100, user_id=201)
        )

    def test_legacy_ownerless_session_is_still_supported(self) -> None:
        registry = SearchSessionRegistry(clock=self.clock)
        registry.register("legacy", query="Bosch")
        self.assertIsNotNone(
            registry.authorize("legacy", chat_id=1, user_id=2)
        )

    def test_ttl_expires_inactive_session(self) -> None:
        registry = SearchSessionRegistry(
            ttl_seconds=30,
            clock=self.clock,
        )
        registry.register("session")
        self.clock.advance(31)
        self.assertIsNone(
            registry.authorize("session", chat_id=None, user_id=None)
        )
        self.assertEqual(len(registry), 0)

    def test_access_refreshes_lru_and_ttl(self) -> None:
        registry = SearchSessionRegistry(
            capacity=2,
            ttl_seconds=30,
            clock=self.clock,
        )
        registry.register("one")
        self.clock.advance(20)
        self.assertIsNotNone(
            registry.authorize("one", chat_id=None, user_id=None)
        )
        self.clock.advance(20)
        self.assertIsNotNone(
            registry.authorize("one", chat_id=None, user_id=None)
        )

    def test_capacity_evicts_least_recently_used(self) -> None:
        registry = SearchSessionRegistry(capacity=2, clock=self.clock)
        registry.register("one")
        registry.register("two")
        registry.authorize("one", chat_id=None, user_id=None)
        registry.register("three")
        self.assertIsNotNone(
            registry.authorize("one", chat_id=None, user_id=None)
        )
        self.assertIsNone(
            registry.authorize("two", chat_id=None, user_id=None)
        )
        self.assertIsNotNone(
            registry.authorize("three", chat_id=None, user_id=None)
        )


class SelectionQueryRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()

    def test_same_product_keeps_separate_user_queries(self) -> None:
        registry = SelectionQueryRegistry(clock=self.clock)
        registry.remember(
            chat_id=1,
            user_id=10,
            product_key="pixel8",
            query="Pixel",
        )
        registry.remember(
            chat_id=2,
            user_id=20,
            product_key="pixel8",
            query="Google Pixel 8 Obsidian",
        )

        self.assertEqual(
            registry.get(chat_id=1, user_id=10, product_key="pixel8"),
            "Pixel",
        )
        self.assertEqual(
            registry.get(chat_id=2, user_id=20, product_key="pixel8"),
            "Google Pixel 8 Obsidian",
        )
        self.assertIsNone(
            registry.get(chat_id=1, user_id=20, product_key="pixel8")
        )

    def test_selection_query_expires(self) -> None:
        registry = SelectionQueryRegistry(
            ttl_seconds=10,
            clock=self.clock,
        )
        registry.remember(
            chat_id=1,
            user_id=1,
            product_key="item",
            query="query",
        )
        self.clock.advance(11)
        self.assertIsNone(
            registry.get(chat_id=1, user_id=1, product_key="item")
        )

    def test_capacity_is_bounded_under_many_users(self) -> None:
        registry = SelectionQueryRegistry(
            capacity=100,
            clock=self.clock,
        )
        for index in range(1_000):
            registry.remember(
                chat_id=index,
                user_id=index,
                product_key=f"product-{index}",
                query=f"query-{index}",
            )
        self.assertEqual(len(registry), 100)
        self.assertIsNone(
            registry.get(chat_id=0, user_id=0, product_key="product-0")
        )
        self.assertEqual(
            registry.get(
                chat_id=999,
                user_id=999,
                product_key="product-999",
            ),
            "query-999",
        )


if __name__ == "__main__":
    unittest.main()
