import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from app.models.catalog import (
    ExternalCatalogItem,
    MasterCatalogProduct,
    MatchLevel,
    ProductIdentity,
)
from app.services.catalog_storage import JsonCatalogStorage


class SqliteCatalogStorage:
    """Транзакционное SQLite-хранилище мастер-каталога."""

    _schema_version = 1
    _migration_statements = {
        1: (
            """
            CREATE TABLE IF NOT EXISTS catalog_products (
                product_key TEXT PRIMARY KEY,
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                brand TEXT,
                model TEXT,
                memory TEXT,
                color TEXT,
                revision TEXT,
                ean TEXT,
                mpn TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS catalog_offers (
                source_key TEXT NOT NULL,
                external_id TEXT NOT NULL,
                product_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                price REAL,
                currency TEXT,
                available INTEGER NOT NULL,
                identity_present INTEGER NOT NULL,
                brand TEXT,
                model TEXT,
                memory TEXT,
                color TEXT,
                revision TEXT,
                ean TEXT,
                mpn TEXT,
                match_level TEXT,
                match_score REAL,
                match_reason TEXT,
                match_conflicts TEXT NOT NULL,
                match_candidate_key TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (source_key, external_id),
                FOREIGN KEY (product_key)
                    REFERENCES catalog_products(product_key)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_catalog_offers_product
            ON catalog_offers(product_key, position)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_catalog_products_title
            ON catalog_products(title)
            """,
        )
    }

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def schema_version(self) -> int:
        self.initialize()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM schema_migrations"
            ).fetchone()
        return int(row["version"])

    def initialize(self) -> None:
        """Создаёт БД и последовательно применяет миграции."""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM schema_migrations"
            ).fetchone()
            current_version = int(row["version"])

            for version in range(current_version + 1, self._schema_version + 1):
                statements = self._migration_statements.get(version)
                if statements is None:
                    raise RuntimeError(
                        f"Missing catalog database migration: {version}"
                    )
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (version, datetime.now().astimezone().isoformat()),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save(self, products: Iterable[MasterCatalogProduct]) -> None:
        """Атомарно заменяет полный снимок каталога."""

        snapshot = tuple(products)
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM catalog_offers")
            connection.execute("DELETE FROM catalog_products")

            for product_position, product in enumerate(snapshot):
                connection.execute(
                    """
                    INSERT INTO catalog_products(
                        product_key, position, title,
                        brand, model, memory, color, revision, ean, mpn
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product.key,
                        product_position,
                        product.title,
                        product.identity.brand,
                        product.identity.model,
                        product.identity.memory,
                        product.identity.color,
                        product.identity.revision,
                        product.identity.ean,
                        product.identity.mpn,
                    ),
                )

                for offer_position, offer in enumerate(product.offers):
                    identity = offer.identity
                    connection.execute(
                        """
                        INSERT INTO catalog_offers(
                            source_key, external_id, product_key, position,
                            source, title, url, price, currency, available,
                            identity_present, brand, model, memory, color,
                            revision, ean, mpn, match_level, match_score,
                            match_reason, match_conflicts,
                            match_candidate_key, updated_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            offer.source.strip().casefold(),
                            offer.external_id.strip(),
                            product.key,
                            offer_position,
                            offer.source,
                            offer.title,
                            offer.url,
                            offer.price,
                            offer.currency,
                            int(offer.available),
                            int(identity is not None),
                            identity.brand if identity is not None else None,
                            identity.model if identity is not None else None,
                            identity.memory if identity is not None else None,
                            identity.color if identity is not None else None,
                            identity.revision if identity is not None else None,
                            identity.ean if identity is not None else None,
                            identity.mpn if identity is not None else None,
                            (
                                offer.match_level.value
                                if offer.match_level is not None
                                else None
                            ),
                            offer.match_score,
                            offer.match_reason,
                            json.dumps(
                                list(offer.match_conflicts),
                                ensure_ascii=False,
                            ),
                            offer.match_candidate_key,
                            offer.updated_at.isoformat(),
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load(self) -> list[MasterCatalogProduct]:
        """Восстанавливает карточки и офферы в исходном порядке."""

        self.initialize()
        with self._connection() as connection:
            product_rows = connection.execute(
                "SELECT * FROM catalog_products ORDER BY position"
            ).fetchall()
            offer_rows = connection.execute(
                "SELECT * FROM catalog_offers "
                "ORDER BY product_key, position"
            ).fetchall()

        offers_by_product: dict[str, list[ExternalCatalogItem]] = {}
        for row in offer_rows:
            identity = None
            if row["identity_present"]:
                identity = ProductIdentity(
                    brand=row["brand"],
                    model=row["model"],
                    memory=row["memory"],
                    color=row["color"],
                    revision=row["revision"],
                    ean=row["ean"],
                    mpn=row["mpn"],
                )
            raw_match_level = row["match_level"]
            offer = ExternalCatalogItem(
                source=row["source"],
                external_id=row["external_id"],
                title=row["title"],
                url=row["url"],
                price=row["price"],
                currency=row["currency"],
                available=bool(row["available"]),
                identity=identity,
                match_level=(
                    MatchLevel(raw_match_level)
                    if raw_match_level is not None
                    else None
                ),
                match_score=row["match_score"],
                match_reason=row["match_reason"],
                match_conflicts=tuple(
                    json.loads(row["match_conflicts"] or "[]")
                ),
                match_candidate_key=row["match_candidate_key"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            offers_by_product.setdefault(row["product_key"], []).append(offer)

        return [
            MasterCatalogProduct(
                key=row["product_key"],
                title=row["title"],
                identity=ProductIdentity(
                    brand=row["brand"],
                    model=row["model"],
                    memory=row["memory"],
                    color=row["color"],
                    revision=row["revision"],
                    ean=row["ean"],
                    mpn=row["mpn"],
                ),
                offers=offers_by_product.get(row["product_key"], []),
            )
            for row in product_rows
        ]

    def is_empty(self) -> bool:
        self.initialize()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM catalog_products"
            ).fetchone()
        return int(row["count"]) == 0

    def import_json_if_empty(
        self,
        json_storage: JsonCatalogStorage,
    ) -> int:
        """Однократно импортирует старый JSON snapshot в пустую БД."""

        if not self.is_empty():
            return 0
        products = json_storage.load()
        if not products:
            return 0
        self.save(products)
        return len(products)

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
