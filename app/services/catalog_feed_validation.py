from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from app.models.catalog import ExternalCatalogItem
from app.models.catalog_feed import CatalogFeedIssue
from app.services.product_identity import ProductIdentityBuilder
from app.services.product_variants import extract_color_key, extract_memory


class CatalogFeedRecordParser:
    """Валидирует одну запись фида и строит внешний товар."""

    def __init__(self) -> None:
        self._identity_builder = ProductIdentityBuilder()

    def parse(
        self,
        record_number: int,
        record: dict[str, Any],
        *,
        default_source: str | None = None,
    ) -> tuple[ExternalCatalogItem | None, tuple[CatalogFeedIssue, ...]]:
        issues: list[CatalogFeedIssue] = []
        source = self._text(record.get("source") or default_source)
        title = self._text(record.get("title") or record.get("name"))
        url = self._text(record.get("url"))

        if source is None:
            issues.append(self._issue(record_number, "source", "source is required"))
        if title is None:
            issues.append(self._issue(record_number, "title", "title is required"))
        if url is None or not self._valid_url(url):
            issues.append(
                self._issue(
                    record_number,
                    "url",
                    "absolute http(s) URL is required",
                )
            )

        price = self._price(record.get("price"), record_number, issues)
        available = self._available(
            record.get("available", True),
            record_number,
            issues,
        )
        updated_at = self._updated_at(
            record.get("updated_at"),
            record_number,
            issues,
        )

        if issues or source is None or title is None or url is None:
            return None, tuple(issues)

        identity_payload = (
            record.get("identity")
            if isinstance(record.get("identity"), dict)
            else {}
        )

        def identity_value(name: str) -> str | None:
            return self._text(record.get(name) or identity_payload.get(name))

        identity = self._identity_builder.build(
            title,
            brand=identity_value("brand"),
            model=identity_value("model"),
            ean=(
                identity_value("ean")
                or identity_value("gtin")
                or identity_value("upc")
            ),
            mpn=identity_value("mpn"),
            revision=identity_value("revision"),
        )
        identity = replace(
            identity,
            memory=self._memory(identity_value("memory")) or identity.memory,
            color=self._color(identity_value("color")) or identity.color,
        )

        external_id = self._text(
            record.get("external_id") or record.get("sku")
        ) or self._external_id(url)
        currency = self._text(record.get("currency"))
        if price is not None:
            currency = (currency or "BYN").upper()

        return (
            ExternalCatalogItem(
                source=source,
                external_id=external_id,
                title=title,
                url=url,
                price=price,
                currency=currency,
                available=available,
                identity=identity,
                updated_at=updated_at,
            ),
            tuple(issues),
        )

    @staticmethod
    def _issue(record: int, field: str, message: str) -> CatalogFeedIssue:
        return CatalogFeedIssue(record=record, field=field, message=message)

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None or isinstance(value, (dict, list, tuple, set)):
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None

    @staticmethod
    def _valid_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _external_id(url: str) -> str:
        payload = url.strip().casefold().encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:24]

    @classmethod
    def _price(
        cls,
        value: Any,
        record: int,
        issues: list[CatalogFeedIssue],
    ) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            issues.append(cls._issue(record, "price", "price must be numeric"))
            return None
        try:
            price = Decimal(str(value).replace(",", "."))
        except (InvalidOperation, ValueError):
            issues.append(cls._issue(record, "price", "price must be numeric"))
            return None
        if not price.is_finite() or price < 0:
            issues.append(
                cls._issue(record, "price", "price must be non-negative")
            )
            return None
        return float(price)

    @classmethod
    def _available(
        cls,
        value: Any,
        record: int,
        issues: list[CatalogFeedIssue],
    ) -> bool:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().casefold()
        if normalized in {"1", "true", "yes", "in_stock", "available"}:
            return True
        if normalized in {"0", "false", "no", "out_of_stock", "unavailable"}:
            return False
        issues.append(
            cls._issue(record, "available", "available must be boolean")
        )
        return False

    @classmethod
    def _updated_at(
        cls,
        value: Any,
        record: int,
        issues: list[CatalogFeedIssue],
    ) -> datetime:
        if value is None or value == "":
            return datetime.now(timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            issues.append(
                cls._issue(record, "updated_at", "updated_at must be ISO-8601")
            )
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _memory(value: str | None) -> str | None:
        if value is None:
            return None
        detected = extract_memory(value)
        if detected is not None:
            return detected
        if value.isdigit():
            return f"{int(value)}GB"
        normalized = re.sub(r"\s+", "", value.upper())
        return normalized.replace("ГБ", "GB").replace("ТБ", "TB") or None

    @staticmethod
    def _color(value: str | None) -> str | None:
        if value is None:
            return None
        detected = extract_color_key(f"({value})")
        if detected is not None:
            return detected
        normalized = re.sub(
            r"[^a-zа-я0-9]+",
            "_",
            value.casefold().replace("ё", "е"),
        ).strip("_")
        return normalized or None
