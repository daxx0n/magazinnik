import asyncio
import unittest

from app.services.price_service import PriceService


class SourceSearchLoadTest(unittest.IsolatedAsyncioTestCase):
    async def test_fifty_unique_source_requests_respect_semaphore(self) -> None:
        service = PriceService()
        service._source_search_semaphore = asyncio.Semaphore(4)
        active = 0
        peak = 0
        lock = asyncio.Lock()

        async def loader(value: int) -> list[int]:
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1
            return [value]

        results = await asyncio.gather(
            *(
                service._cached_source_search(
                    source_name="test",
                    query=f"product-{index}",
                    limit=10,
                    loader=lambda index=index: loader(index),
                )
                for index in range(50)
            )
        )

        self.assertEqual(results, [[index] for index in range(50)])
        self.assertLessEqual(peak, 4)
        self.assertEqual(service._source_search_tasks, {})

    async def test_fifty_identical_source_requests_share_one_loader(self) -> None:
        service = PriceService()
        service._source_search_semaphore = asyncio.Semaphore(4)
        calls = 0

        async def loader() -> list[str]:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.02)
            return ["result"]

        results = await asyncio.gather(
            *(
                service._cached_source_search(
                    source_name="test",
                    query="  Google   Pixel 8 ",
                    limit=10,
                    loader=loader,
                )
                for _ in range(50)
            )
        )

        self.assertEqual(results, [["result"]] * 50)
        self.assertEqual(calls, 1)
        self.assertEqual(service._source_search_tasks, {})

    async def test_cancelled_waiter_does_not_cancel_source_loader(self) -> None:
        service = PriceService()
        service._source_search_semaphore = asyncio.Semaphore(1)
        started = asyncio.Event()
        release = asyncio.Event()

        async def loader() -> list[str]:
            started.set()
            await release.wait()
            return ["done"]

        first = asyncio.create_task(
            service._cached_source_search("test", "same", 1, loader)
        )
        second = asyncio.create_task(
            service._cached_source_search("test", "same", 1, loader)
        )
        await started.wait()
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertEqual(await second, ["done"])


if __name__ == "__main__":
    unittest.main()
