import json
import os
import unittest

from app.services.catalog_first_search import CatalogFirstPriceService
from app.sources.twenty_one_vek import TwentyOneVekSource


class LiveTwentyOneVekY63Diagnostic(unittest.IsolatedAsyncioTestCase):
    async def test_dump_live_candidates_and_reasons(self) -> None:
        canonical = "Huawei nova Y63 6GB/128GB"
        offers = await TwentyOneVekSource().find_offers(
            "Huawei nova Y63 6 128GB",
            limit=100,
        )
        rows = [
            {
                "title": offer.title,
                "reason": CatalogFirstPriceService._model_mismatch_reason(
                    canonical_title=canonical,
                    candidate_title=offer.title,
                    requested_title=canonical,
                ),
                "url": offer.url,
            }
            for offer in offers
        ]
        os.makedirs("diagnostic", exist_ok=True)
        with open("diagnostic/21vek-y63.json", "w", encoding="utf-8") as file:
            json.dump(rows, file, ensure_ascii=False, indent=2)
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
