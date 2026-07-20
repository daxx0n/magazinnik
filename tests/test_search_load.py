import asyncio
import unittest

from app.services.search_load import (
    SearchBusyError,
    SearchRequestCoordinator,
)


class SearchRequestCoordinatorTest(unittest.IsolatedAsyncioTestCase):
    async def test_fifty_unique_users_respect_global_concurrency(self) -> None:
        coordinator: SearchRequestCoordinator[str, int] = (
            SearchRequestCoordinator(max_concurrent=5, max_pending=100)
        )
        active = 0
        peak = 0
        lock = asyncio.Lock()

        async def loader(value: int) -> int:
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1
            return value

        results = await asyncio.gather(
            *(
                coordinator.run(
                    f"user-{index}",
                    lambda index=index: loader(index),
                )
                for index in range(50)
            )
        )

        self.assertEqual(results, list(range(50)))
        self.assertLessEqual(peak, 5)
        self.assertLessEqual(coordinator.peak_active, 5)
        self.assertEqual(coordinator.pending_count, 0)

    async def test_identical_requests_are_coalesced(self) -> None:
        coordinator: SearchRequestCoordinator[str, str] = (
            SearchRequestCoordinator(max_concurrent=3, max_pending=100)
        )
        calls = 0

        async def loader() -> str:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.02)
            return "ok"

        results = await asyncio.gather(
            *(coordinator.run("pixel-8", loader) for _ in range(50))
        )

        self.assertEqual(results, ["ok"] * 50)
        self.assertEqual(calls, 1)

    async def test_cancelled_waiter_does_not_cancel_shared_search(self) -> None:
        coordinator: SearchRequestCoordinator[str, str] = (
            SearchRequestCoordinator(max_concurrent=1, max_pending=10)
        )
        started = asyncio.Event()
        release = asyncio.Event()

        async def loader() -> str:
            started.set()
            await release.wait()
            return "finished"

        first = asyncio.create_task(coordinator.run("same", loader))
        second = asyncio.create_task(coordinator.run("same", loader))
        await started.wait()
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertEqual(await second, "finished")

    async def test_pending_limit_fails_fast(self) -> None:
        coordinator: SearchRequestCoordinator[str, str] = (
            SearchRequestCoordinator(max_concurrent=1, max_pending=2)
        )
        release = asyncio.Event()

        async def loader() -> str:
            await release.wait()
            return "ok"

        first = asyncio.create_task(coordinator.run("one", loader))
        second = asyncio.create_task(coordinator.run("two", loader))
        await asyncio.sleep(0)
        with self.assertRaises(SearchBusyError):
            await coordinator.run("three", loader)
        release.set()
        self.assertEqual(await first, "ok")
        self.assertEqual(await second, "ok")


if __name__ == "__main__":
    unittest.main()
