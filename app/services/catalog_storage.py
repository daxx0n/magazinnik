import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.catalog import (
    ExternalCatalogItem,
    MasterCatalogProduct,
    MatchLevel,
    ProductIdentity,
)


class JsonCatalogStorage:
    """Сохраняет мастер-каталог в атомарно заменяемый JSON-файл."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, products: Iterable[MasterCatalogProduct]) -> None:
        """Атомарно записывает полный снимок каталога."""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = [
            self._serialize_product(product)
            for product in products
        ]
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self._path)

    def load(self) -> list[MasterCatalogProduct]:
        """Загружает снимок или возвращает пустой каталог."""

        if not self._path.exists():
            return []

        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Catalog snapshot must contain a list")
        return [self._deserialize_product(item) for item in payload]

    @staticmethod
    def _serialize_product(
        product: MasterCatalogProduct,
    ) -> dict[str, Any]:
        payload = asdict(product)
        for offer in payload["offers"]:
            updated_at = offer.get("updated_at")
            if isinstance(updated_at, datetime):
                offer["updated_at"] = updated_at.isoformat()
        return payload

    @staticmethod
    def _deserialize_product(
        payload: dict[str, Any],
    ) -> MasterCatalogProduct:
        identity = ProductIdentity(**payload["identity"])
        offers = []
        for raw_offer in payload.get("offers", []):
            offer_payload = dict(raw_offer)
            raw_identity = offer_payload.get("identity")
            if raw_identity is not None:
                offer_payload["identity"] = ProductIdentity(**raw_identity)

            raw_match_level = offer_payload.get("match_level")
            if raw_match_level:
                offer_payload["match_level"] = MatchLevel(raw_match_level)

            raw_conflicts = offer_payload.get("match_conflicts")
            if raw_conflicts is not None:
                offer_payload["match_conflicts"] = tuple(raw_conflicts)

            raw_updated_at = offer_payload.get("updated_at")
            if raw_updated_at:
                offer_payload["updated_at"] = datetime.fromisoformat(
                    raw_updated_at
                )
            offers.append(ExternalCatalogItem(**offer_payload))

        return MasterCatalogProduct(
            key=payload["key"],
            title=payload["title"],
            identity=identity,
            offers=offers,
        )
