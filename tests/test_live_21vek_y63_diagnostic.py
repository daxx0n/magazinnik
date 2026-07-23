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
            (
                offer.title,
                CatalogFirstPriceService._model_mismatch_reason(
                    canonical_title=canonical,
                    candidate_title=offer.title,
                    requested_title=canonical,
                ),
                offer.url,
            )
            for offer in offers
        ]
        self.fail(f"LIVE_21VEK_Y63={rows!r}")


if __name__ == "__main__":
    unittest.main()
