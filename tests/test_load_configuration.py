import os
import unittest
from unittest.mock import patch

from app.services.price_service import PriceService
from app.services.search_input import normalize_search_query
from app.services.search_load import SearchRequestCoordinator


class LoadConfigurationTest(unittest.TestCase):
    def test_invalid_explicit_coordinator_values_use_safe_defaults(self) -> None:
        coordinator = SearchRequestCoordinator(
            max_concurrent=0,
            max_pending=-1,
        )
        self.assertEqual(coordinator.max_concurrent, 8)
        self.assertEqual(coordinator.max_pending, 200)

    def test_pending_capacity_cannot_be_below_active_capacity(self) -> None:
        coordinator = SearchRequestCoordinator(
            max_concurrent=10,
            max_pending=3,
        )
        self.assertEqual(coordinator.max_concurrent, 10)
        self.assertEqual(coordinator.max_pending, 10)

    def test_invalid_environment_values_use_safe_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SEARCH_MAX_CONCURRENT_COMPARISONS": "not-a-number",
                "SEARCH_MAX_PENDING_COMPARISONS": "0",
            },
            clear=False,
        ):
            coordinator = SearchRequestCoordinator()

        self.assertEqual(coordinator.max_concurrent, 8)
        self.assertEqual(coordinator.max_pending, 200)

    def test_valid_environment_values_are_applied(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SEARCH_MAX_CONCURRENT_COMPARISONS": "6",
                "SEARCH_MAX_PENDING_COMPARISONS": "60",
            },
            clear=False,
        ):
            coordinator = SearchRequestCoordinator()

        self.assertEqual(coordinator.max_concurrent, 6)
        self.assertEqual(coordinator.max_pending, 60)

    def test_source_concurrency_parser_rejects_invalid_values(self) -> None:
        with patch.dict(
            os.environ,
            {"SOURCE_SEARCH_MAX_CONCURRENCY": "broken"},
            clear=False,
        ):
            self.assertEqual(
                PriceService._positive_environment_int(
                    "SOURCE_SEARCH_MAX_CONCURRENCY",
                    12,
                ),
                12,
            )

        with patch.dict(
            os.environ,
            {"SOURCE_SEARCH_MAX_CONCURRENCY": "-4"},
            clear=False,
        ):
            self.assertEqual(
                PriceService._positive_environment_int(
                    "SOURCE_SEARCH_MAX_CONCURRENCY",
                    12,
                ),
                12,
            )

    def test_too_small_query_limit_does_not_break_search(self) -> None:
        with patch.dict(
            os.environ,
            {"SEARCH_MAX_QUERY_LENGTH": "5"},
            clear=False,
        ):
            self.assertEqual(
                normalize_search_query("Google Pixel 8"),
                "Google Pixel 8",
            )


if __name__ == "__main__":
    unittest.main()
