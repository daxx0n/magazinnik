import json
import os
import unittest
from unittest.mock import patch

from app.handlers.catalog_feed import (
    command_argument,
    format_bytes,
    format_catalog_feed_report,
    parse_catalog_feed_caption,
)
from app.services.catalog_feed_upload import (
    CatalogFeedSessionForbidden,
    CatalogFeedSessionNotFound,
    CatalogFeedUploadConfig,
    CatalogFeedUploadManager,
)
from app.services.catalog_service import CatalogService
from app.services.master_catalog import MasterCatalog


class CatalogFeedUploadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock_value = 1000.0
        self.service = CatalogService(
            catalog=MasterCatalog(),
            restore_on_start=False,
        )
        self.manager = CatalogFeedUploadManager(
            self.service,
            config=CatalogFeedUploadConfig(
                max_file_bytes=1024,
                confirmation_ttl_seconds=60,
                max_pending_sessions=2,
            ),
            clock=lambda: self.clock_value,
        )

    @staticmethod
    def feed(title: str = "Google Pixel 8") -> str:
        return json.dumps(
            {
                "source": "Supplier",
                "title": title,
                "url": "https://example.com/pixel-8",
                "price": 1000,
                "ean": "0840244700001",
            }
        )

    def prepare(self, **overrides):
        values = {
            "chat_id": 10,
            "user_id": 20,
            "filename": "feed.json",
            "text": self.feed(),
        }
        values.update(overrides)
        return self.manager.prepare(**values)

    def test_prepare_runs_dry_run_without_mutating_catalog(self) -> None:
        session, report = self.prepare()

        self.assertIsNotNone(session)
        self.assertEqual(report.status, "dry_run")
        self.assertEqual(report.valid_records, 1)
        self.assertEqual(report.created_products, 1)
        self.assertEqual(self.service.catalog.products, ())
        self.assertEqual(self.manager.pending_count, 1)

    def test_confirm_imports_once_and_consumes_token(self) -> None:
        session, _ = self.prepare()
        assert session is not None

        report = self.manager.confirm(
            session.token,
            chat_id=10,
            user_id=20,
        )

        self.assertEqual(report.status, "imported")
        self.assertEqual(len(self.service.catalog.products), 1)
        self.assertEqual(self.manager.pending_count, 0)
        with self.assertRaises(CatalogFeedSessionNotFound):
            self.manager.confirm(
                session.token,
                chat_id=10,
                user_id=20,
            )

    def test_wrong_user_cannot_confirm_and_session_remains(self) -> None:
        session, _ = self.prepare()
        assert session is not None

        with self.assertRaises(CatalogFeedSessionForbidden):
            self.manager.confirm(
                session.token,
                chat_id=10,
                user_id=999,
            )

        self.assertEqual(self.manager.pending_count, 1)
        self.assertEqual(self.service.catalog.products, ())

    def test_wrong_chat_cannot_cancel(self) -> None:
        session, _ = self.prepare()
        assert session is not None

        with self.assertRaises(CatalogFeedSessionForbidden):
            self.manager.cancel(
                session.token,
                chat_id=999,
                user_id=20,
            )

        self.assertEqual(self.manager.pending_count, 1)

    def test_expired_session_is_removed(self) -> None:
        session, _ = self.prepare()
        assert session is not None
        self.clock_value += 61

        with self.assertRaises(CatalogFeedSessionNotFound):
            self.manager.confirm(
                session.token,
                chat_id=10,
                user_id=20,
            )

        self.assertEqual(self.manager.pending_count, 0)

    def test_pending_limit_evicts_oldest_session(self) -> None:
        first, _ = self.prepare(filename="first.json")
        self.clock_value += 1
        second, _ = self.prepare(filename="second.json")
        self.clock_value += 1
        third, _ = self.prepare(filename="third.json")
        assert first is not None
        assert second is not None
        assert third is not None

        self.assertEqual(self.manager.pending_count, 2)
        with self.assertRaises(CatalogFeedSessionNotFound):
            self.manager.confirm(
                first.token,
                chat_id=10,
                user_id=20,
            )
        self.manager.cancel(second.token, chat_id=10, user_id=20)
        self.manager.cancel(third.token, chat_id=10, user_id=20)

    def test_invalid_feed_does_not_create_session(self) -> None:
        session, report = self.prepare(text="{broken")

        self.assertIsNone(session)
        self.assertEqual(report.invalid_records, 1)
        self.assertEqual(self.manager.pending_count, 0)

    def test_empty_feed_does_not_create_session(self) -> None:
        session, report = self.prepare(text="   ")

        self.assertIsNone(session)
        self.assertEqual(report.valid_records, 0)
        self.assertEqual(self.manager.pending_count, 0)

    def test_supported_extensions_are_strict(self) -> None:
        self.assertEqual(
            self.manager.format_from_filename("feed.JSON"),
            "json",
        )
        self.assertEqual(
            self.manager.format_from_filename("feed.ndjson"),
            "jsonl",
        )
        with self.assertRaises(ValueError):
            self.manager.format_from_filename("feed.csv")

    def test_environment_config_is_clamped(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CATALOG_FEED_MAX_BYTES": "999999999",
                "CATALOG_FEED_CONFIRM_TTL_SECONDS": "5",
                "CATALOG_FEED_MAX_PENDING": "0",
            },
            clear=False,
        ):
            config = CatalogFeedUploadConfig.from_environment()

        self.assertEqual(config.max_file_bytes, 10 * 1024 * 1024)
        self.assertEqual(config.confirmation_ttl_seconds, 60.0)
        self.assertEqual(config.max_pending_sessions, 1)

    def test_caption_and_command_helpers(self) -> None:
        self.assertEqual(
            parse_catalog_feed_caption("/catalog_feed Supplier A"),
            "Supplier A",
        )
        self.assertEqual(
            parse_catalog_feed_caption("/catalog_feed@my_bot"),
            "",
        )
        self.assertIsNone(parse_catalog_feed_caption("ordinary document"))
        self.assertEqual(command_argument("/catalog_feed_confirm AbC123"), "abc123")
        self.assertIsNone(command_argument("/catalog_feed_confirm"))

    def test_formats_dry_run_report_and_sizes(self) -> None:
        _, report = self.prepare()
        text = format_catalog_feed_report(report, title="Dry-run")

        self.assertIn("Dry-run", text)
        self.assertIn("Валидных: 1", text)
        self.assertIn("Новых карточек: 1", text)
        self.assertEqual(format_bytes(1024), "1.0 КБ")
        self.assertEqual(format_bytes(2 * 1024 * 1024), "2.0 МБ")


if __name__ == "__main__":
    unittest.main()
