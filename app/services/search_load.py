from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable, Hashable
from typing import Generic, TypeVar


SearchKey = TypeVar("SearchKey", bound=Hashable)
SearchResult = TypeVar("SearchResult")


class SearchBusyError(RuntimeError):
    """Очередь пользовательских поисков достигла безопасного лимита."""


class SearchRequestCoordinator(Generic[SearchKey, SearchResult]):
    """Ограничивает нагрузку и объединяет одинаковые параллельные запросы."""

    def __init__(
        self,
        *,
        max_concurrent: int | None = None,
        max_pending: int | None = None,
    ) -> None:
        self.max_concurrent = self._positive_int(
            max_concurrent,
            os.getenv("SEARCH_MAX_CONCURRENT_COMPARISONS"),
            8,
        )
        self.max_pending = self._positive_int(
            max_pending,
            os.getenv("SEARCH_MAX_PENDING_COMPARISONS"),
            200,
        )
        if self.max_pending < self.max_concurrent:
            self.max_pending = self.max_concurrent

        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._tasks: dict[SearchKey, asyncio.Task[SearchResult]] = {}
        self._active = 0
        self._peak_active = 0

    @property
    def pending_count(self) -> int:
        return len(self._tasks)

    @property
    def active_count(self) -> int:
        return self._active

    @property
    def peak_active(self) -> int:
        return self._peak_active

    async def run(
        self,
        key: SearchKey,
        loader: Callable[[], Awaitable[SearchResult]],
    ) -> SearchResult:
        """Возвращает общий task для одинакового ключа и ограничивает fan-out."""

        task = self._tasks.get(key)
        if task is None:
            if len(self._tasks) >= self.max_pending:
                raise SearchBusyError(
                    "Слишком много поисков выполняется одновременно."
                )
            task = asyncio.create_task(
                self._execute(loader),
                name="coordinated-product-search",
            )
            self._tasks[key] = task
            task.add_done_callback(
                lambda completed, task_key=key: self._forget(
                    task_key,
                    completed,
                )
            )

        return await asyncio.shield(task)

    async def _execute(
        self,
        loader: Callable[[], Awaitable[SearchResult]],
    ) -> SearchResult:
        async with self._semaphore:
            self._active += 1
            self._peak_active = max(self._peak_active, self._active)
            try:
                return await loader()
            finally:
                self._active -= 1

    def _forget(
        self,
        key: SearchKey,
        task: asyncio.Task[SearchResult],
    ) -> None:
        if self._tasks.get(key) is task:
            self._tasks.pop(key, None)
        if task.cancelled():
            return
        with contextlib.suppress(Exception):
            task.exception()

    @staticmethod
    def _positive_int(
        explicit: int | None,
        raw_environment: str | None,
        default: int,
    ) -> int:
        if explicit is not None:
            return explicit if explicit > 0 else default
        try:
            parsed = int((raw_environment or "").strip())
        except ValueError:
            return default
        return parsed if parsed > 0 else default
