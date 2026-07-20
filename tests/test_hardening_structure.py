import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HardeningStructureTest(unittest.TestCase):
    def test_catalog_async_ingest_is_defined_once(self) -> None:
        text = (ROOT / "app/services/catalog_service.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            text.count("def ingest_offers_with_report_async("),
            1,
        )
        self.assertNotIn(
            "@synchronized\n    async def ingest_offers_with_report_async(",
            text,
        )

    def test_price_service_load_helpers_are_defined_once(self) -> None:
        text = (ROOT / "app/services/price_service.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            text.count("_source_search_semaphore = asyncio.Semaphore("),
            1,
        )
        self.assertEqual(text.count("def _run_limited_source_loader("), 1)
        self.assertEqual(text.count("def _positive_environment_int("), 1)

    def test_search_registries_and_busy_handlers_are_not_duplicated(self) -> None:
        text = (ROOT / "app/handlers/search.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            text.count("product_session_registry = SearchSessionRegistry("),
            1,
        )
        self.assertEqual(
            text.count("category_session_registry = SearchSessionRegistry("),
            1,
        )
        self.assertEqual(
            text.count("selection_query_registry = SelectionQueryRegistry("),
            1,
        )
        self.assertEqual(
            text.count("category_discovery_coordinator:"),
            1,
        )
        self.assertEqual(
            text.count("product_discovery_coordinator:"),
            1,
        )
        self.assertNotIn(
            "except SearchBusyError:\n"
            "        await message.edit_text(\n"
            "            \"Сейчас выполняется слишком много сравнений. \"\n"
            "            \"Попробуй ещё раз через несколько секунд.\"\n"
            "        )\n"
            "        return\n"
            "    except SearchBusyError:",
            text,
        )


if __name__ == "__main__":
    unittest.main()
