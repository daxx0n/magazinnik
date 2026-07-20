from __future__ import annotations

import os
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from app.models.catalog_feed import CatalogFeedImportReport
from app.services.catalog_feed_import import CatalogFeedImporter
from app.services.catalog_service import CatalogService


class CatalogFeedSessionError(ValueError):
    """Базовая ошибка подтверждения загруженного фида."""


class CatalogFeedSessionNotFound(CatalogFeedSessionError):
    """Одноразовая сессия отсутствует или уже использована."""


class CatalogFeedSessionForbidden(CatalogFeedSessionError):
    """Сессия принадлежит другому пользователю или чату."""


@dataclass(frozen=True, slots=True)
class CatalogFeedUploadConfig:
    """Ограничения безопасной загрузки фидов через Telegram."""

    max_file_bytes: int = 2 * 1024 * 1024
    confirmation_ttl_seconds: float = 900.0
    max_pending_sessions: int = 20

    @classmethod
    def from_environment(cls) -> CatalogFeedUploadConfig:
        return cls(
            max_file_bytes=_env_int(
                "CATALOG_FEED_MAX_BYTES",
                default=2 * 1024 * 1024,
                minimum=1024,
                maximum=10 * 1024 * 1024,
            ),
            confirmation_ttl_seconds=float(
                _env_int(
                    "CATALOG_FEED_CONFIRM_TTL_SECONDS",
                    default=900,
                    minimum=60,
                    maximum=3600,
                )
            ),
            max_pending_sessions=_env_int(
                "CATALOG_FEED_MAX_PENDING",
                default=20,
                minimum=1,
                maximum=100,
            ),
        )


@dataclass(frozen=True, slots=True)
class CatalogFeedUploadSession:
    """Проверенный фид, ожидающий одноразового подтверждения."""

    token: str
    chat_id: int
    user_id: int
    filename: str
    text: str
    format_hint: str
    default_source: str | None
    snapshot: bool
    created_at: float
    dry_run_report: CatalogFeedImportReport


class CatalogFeedUploadManager:
    """Хранит короткоживущие dry-run сессии и подтверждает импорт."""

    def __init__(
        self,
        catalog_service: CatalogService,
        config: CatalogFeedUploadConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._importer = CatalogFeedImporter(catalog_service)
        self._config = config or CatalogFeedUploadConfig.from_environment()
        self._clock = clock
        self._sessions: OrderedDict[str, CatalogFeedUploadSession] = (
            OrderedDict()
        )

    @property
    def config(self) -> CatalogFeedUploadConfig:
        return self._config

    @property
    def pending_count(self) -> int:
        self._cleanup()
        return len(self._sessions)

    def prepare(
        self,
        *,
        chat_id: int,
        user_id: int,
        filename: str,
        text: str,
        default_source: str | None = None,
        snapshot: bool = False,
    ) -> tuple[
        CatalogFeedUploadSession | None,
        CatalogFeedImportReport,
    ]:
        """Запускает dry-run и создаёт сессию только для валидного фида."""

        self._cleanup()
        format_hint = self.format_from_filename(filename)
        report = self._importer.import_text(
            text,
            dry_run=True,
            allow_partial=False,
            snapshot=snapshot,
            default_source=default_source,
            format_hint=format_hint,
        )
        if report.invalid_records or not report.valid_records:
            return None, report

        token = self._new_token()
        session = CatalogFeedUploadSession(
            token=token,
            chat_id=chat_id,
            user_id=user_id,
            filename=filename,
            text=text,
            format_hint=format_hint,
            default_source=default_source,
            snapshot=snapshot,
            created_at=self._clock(),
            dry_run_report=report,
        )
        self._sessions[token] = session
        self._sessions.move_to_end(token)
        while len(self._sessions) > self._config.max_pending_sessions:
            self._sessions.popitem(last=False)
        return session, report

    def confirm(
        self,
        token: str,
        *,
        chat_id: int,
        user_id: int,
    ) -> CatalogFeedImportReport:
        """Одноразово импортирует ранее проверенный фид."""

        session = self._require_session(token, chat_id, user_id)
        self._sessions.pop(token, None)
        return self._importer.import_text(
            session.text,
            dry_run=False,
            allow_partial=False,
            snapshot=session.snapshot,
            default_source=session.default_source,
            format_hint=session.format_hint,
        )

    def cancel(
        self,
        token: str,
        *,
        chat_id: int,
        user_id: int,
    ) -> CatalogFeedUploadSession:
        """Удаляет ожидающий фид без изменения каталога."""

        session = self._require_session(token, chat_id, user_id)
        self._sessions.pop(token, None)
        return session

    @staticmethod
    def format_from_filename(filename: str) -> str:
        normalized = filename.strip().casefold()
        if normalized.endswith((".jsonl", ".ndjson")):
            return "jsonl"
        if normalized.endswith(".json"):
            return "json"
        raise ValueError("Поддерживаются только .json, .jsonl и .ndjson")

    def _require_session(
        self,
        token: str,
        chat_id: int,
        user_id: int,
    ) -> CatalogFeedUploadSession:
        self._cleanup()
        normalized_token = token.strip().casefold()
        session = self._sessions.get(normalized_token)
        if session is None:
            raise CatalogFeedSessionNotFound(
                "Сессия не найдена, истекла или уже использована."
            )
        if session.chat_id != chat_id or session.user_id != user_id:
            raise CatalogFeedSessionForbidden(
                "Эта сессия принадлежит другому пользователю."
            )
        return session

    def _cleanup(self) -> None:
        threshold = self._clock() - self._config.confirmation_ttl_seconds
        expired_tokens = [
            token
            for token, session in self._sessions.items()
            if session.created_at <= threshold
        ]
        for token in expired_tokens:
            self._sessions.pop(token, None)

    def _new_token(self) -> str:
        while True:
            token = secrets.token_hex(4)
            if token not in self._sessions:
                return token


def _env_int(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)
