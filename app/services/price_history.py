import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models.offer import ProductOffer


@dataclass(frozen=True, slots=True)
class PriceAlert:
    chat_id: int
    product_key: str
    title: str
    query: str
    last_notified_price: float
    currency: str


@dataclass(frozen=True, slots=True)
class PricePoint:
    observed_at: str
    price: float
    currency: str
    source: str


class PriceHistoryRepository:
    """Хранит историю минимальных цен и подписки SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS price_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    seller TEXT,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    url TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS
                    idx_price_observations_product_time
                ON price_observations(product_key, observed_at DESC);

                CREATE TABLE IF NOT EXISTS price_alerts (
                    chat_id INTEGER NOT NULL,
                    product_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    query TEXT NOT NULL,
                    last_notified_price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    checked_at TEXT,
                    PRIMARY KEY(chat_id, product_key)
                );
                """
            )

    def record_offers(
        self,
        product_key: str,
        title: str,
        offers: list[ProductOffer],
        observed_at: str | None = None,
    ) -> None:
        if not offers:
            return

        timestamp = observed_at or self._timestamp()

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO price_observations (
                    product_key, title, source, seller, price,
                    currency, url, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        product_key,
                        title,
                        offer.source,
                        offer.seller,
                        float(offer.price),
                        offer.currency,
                        offer.url,
                        timestamp,
                    )
                    for offer in offers
                ],
            )

    def history(
        self,
        product_key: str,
        limit: int = 10,
    ) -> list[PricePoint]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    observed_at, price AS min_price, currency, source
                FROM (
                    SELECT
                        observed_at, price, currency, source,
                        ROW_NUMBER() OVER (
                            PARTITION BY observed_at, currency
                            ORDER BY price, id
                        ) AS price_rank
                    FROM price_observations
                    WHERE product_key = ?
                )
                WHERE price_rank = 1
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (product_key, limit),
            ).fetchall()

        return [
            PricePoint(
                observed_at=row["observed_at"],
                price=row["min_price"],
                currency=row["currency"],
                source=row["source"],
            )
            for row in rows
        ]

    def toggle_alert(
        self,
        chat_id: int,
        product_key: str,
        title: str,
        query: str,
        current_price: float,
        currency: str,
    ) -> bool:
        """Включает подписку или отключает существующую."""

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT active FROM price_alerts
                WHERE chat_id = ? AND product_key = ?
                """,
                (chat_id, product_key),
            ).fetchone()

            if existing is not None and existing["active"]:
                connection.execute(
                    """
                    UPDATE price_alerts SET active = 0
                    WHERE chat_id = ? AND product_key = ?
                    """,
                    (chat_id, product_key),
                )
                return False

            connection.execute(
                """
                INSERT INTO price_alerts (
                    chat_id, product_key, title, query,
                    last_notified_price, currency, active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(chat_id, product_key) DO UPDATE SET
                    title = excluded.title,
                    query = excluded.query,
                    last_notified_price = excluded.last_notified_price,
                    currency = excluded.currency,
                    active = 1,
                    checked_at = NULL
                """,
                (
                    chat_id,
                    product_key,
                    title,
                    query,
                    current_price,
                    currency,
                    self._timestamp(),
                ),
            )
            return True

    def active_alerts(self) -> list[PriceAlert]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chat_id, product_key, title, query,
                       last_notified_price, currency
                FROM price_alerts
                WHERE active = 1
                ORDER BY created_at
                """
            ).fetchall()

        return [PriceAlert(**dict(row)) for row in rows]

    def mark_checked(
        self,
        alert: PriceAlert,
        notified_price: float | None = None,
    ) -> None:
        with self._connect() as connection:
            if notified_price is None:
                connection.execute(
                    """
                    UPDATE price_alerts SET checked_at = ?
                    WHERE chat_id = ? AND product_key = ?
                    """,
                    (self._timestamp(), alert.chat_id, alert.product_key),
                )
            else:
                connection.execute(
                    """
                    UPDATE price_alerts
                    SET checked_at = ?, last_notified_price = ?
                    WHERE chat_id = ? AND product_key = ?
                    """,
                    (
                        self._timestamp(),
                        notified_price,
                        alert.chat_id,
                        alert.product_key,
                    ),
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
