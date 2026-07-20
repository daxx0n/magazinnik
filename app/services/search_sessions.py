from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Callable


@dataclass(frozen=True, slots=True)
class SearchSessionMetadata:
    query: str
    owner_chat_id: int | None
    owner_user_id: int | None
    created_at: float
    accessed_at: float


class SearchSessionRegistry:
    """Хранит TTL и владельца callback-сессии, используя LRU-вытеснение."""

    def __init__(
        self,
        *,
        capacity: int = 1_000,
        ttl_seconds: float = 1_800.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = max(1, capacity)
        self.ttl_seconds = max(1.0, ttl_seconds)
        self._clock = clock
        self._sessions: OrderedDict[str, SearchSessionMetadata] = OrderedDict()

    def register(
        self,
        session_id: str,
        *,
        query: str = "",
        owner_chat_id: int | None = None,
        owner_user_id: int | None = None,
    ) -> None:
        now = self._clock()
        self.prune(now=now)
        self._sessions[session_id] = SearchSessionMetadata(
            query=query,
            owner_chat_id=owner_chat_id,
            owner_user_id=owner_user_id,
            created_at=now,
            accessed_at=now,
        )
        self._sessions.move_to_end(session_id)
        while len(self._sessions) > self.capacity:
            self._sessions.popitem(last=False)

    def authorize(
        self,
        session_id: str,
        *,
        chat_id: int | None,
        user_id: int | None,
    ) -> SearchSessionMetadata | None:
        now = self._clock()
        metadata = self._sessions.get(session_id)
        if metadata is None:
            return None
        if now - metadata.accessed_at > self.ttl_seconds:
            self._sessions.pop(session_id, None)
            return None
        if (
            metadata.owner_chat_id is not None
            and metadata.owner_chat_id != chat_id
        ):
            return None
        if (
            metadata.owner_user_id is not None
            and metadata.owner_user_id != user_id
        ):
            return None

        metadata = replace(metadata, accessed_at=now)
        self._sessions[session_id] = metadata
        self._sessions.move_to_end(session_id)
        return metadata

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def prune(self, *, now: float | None = None) -> int:
        current = self._clock() if now is None else now
        expired = [
            session_id
            for session_id, metadata in self._sessions.items()
            if current - metadata.accessed_at > self.ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
        return len(expired)

    def __len__(self) -> int:
        return len(self._sessions)


class SelectionQueryRegistry:
    """Связывает выбранную карточку с исходным запросом конкретного клиента."""

    def __init__(
        self,
        *,
        capacity: int = 10_000,
        ttl_seconds: float = 1_800.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = max(1, capacity)
        self.ttl_seconds = max(1.0, ttl_seconds)
        self._clock = clock
        self._queries: OrderedDict[
            tuple[int | None, int | None, str],
            tuple[float, str],
        ] = OrderedDict()

    def remember(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        product_key: str,
        query: str,
    ) -> None:
        now = self._clock()
        self.prune(now=now)
        key = (chat_id, user_id, product_key)
        self._queries[key] = (now, query)
        self._queries.move_to_end(key)
        while len(self._queries) > self.capacity:
            self._queries.popitem(last=False)

    def get(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        product_key: str,
    ) -> str | None:
        key = (chat_id, user_id, product_key)
        value = self._queries.get(key)
        if value is None:
            return None
        accessed_at, query = value
        now = self._clock()
        if now - accessed_at > self.ttl_seconds:
            self._queries.pop(key, None)
            return None
        self._queries[key] = (now, query)
        self._queries.move_to_end(key)
        return query

    def prune(self, *, now: float | None = None) -> int:
        current = self._clock() if now is None else now
        expired = [
            key
            for key, (accessed_at, _) in self._queries.items()
            if current - accessed_at > self.ttl_seconds
        ]
        for key in expired:
            self._queries.pop(key, None)
        return len(expired)

    def __len__(self) -> int:
        return len(self._queries)
