from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.models.catalog import CatalogIngestReport
from app.models.catalog_feed import (
    CatalogFeedImportReport,
    CatalogFeedIssue,
)
from app.services.catalog_feed_validation import CatalogFeedRecordParser
from app.services.catalog_service import CatalogService
from app.services.master_catalog import MasterCatalog


class CatalogFeedImporter:
    """Импортирует JSON/JSONL-фиды в мастер-каталог."""

    def __init__(self, catalog_service: CatalogService) -> None:
        self._catalog_service = catalog_service
        self._record_parser = CatalogFeedRecordParser()

    def import_file(
        self,
        path: str | Path,
        *,
        dry_run: bool = False,
        allow_partial: bool = False,
        snapshot: bool = False,
        default_source: str | None = None,
        format_hint: str | None = None,
    ) -> CatalogFeedImportReport:
        feed_path = Path(path)
        hint = format_hint or self._format_from_suffix(feed_path.suffix)
        return self.import_text(
            feed_path.read_text(encoding="utf-8"),
            dry_run=dry_run,
            allow_partial=allow_partial,
            snapshot=snapshot,
            default_source=default_source,
            format_hint=hint,
        )

    def import_text(
        self,
        text: str,
        *,
        dry_run: bool = False,
        allow_partial: bool = False,
        snapshot: bool = False,
        default_source: str | None = None,
        format_hint: str | None = None,
    ) -> CatalogFeedImportReport:
        if snapshot and allow_partial:
            raise ValueError("Snapshot import cannot use partial mode")

        records, parse_issues, total_records = self._decode_records(
            text,
            format_hint=format_hint,
        )
        items = []
        issues = list(parse_issues)

        for record_number, record in records:
            item, record_issues = self._record_parser.parse(
                record_number,
                record,
                default_source=default_source,
            )
            issues.extend(record_issues)
            if item is not None:
                items.append(item)

        snapshot_source = None
        if snapshot:
            if not items:
                issues.append(
                    CatalogFeedIssue(
                        1,
                        "snapshot",
                        "snapshot requires at least one valid record",
                    )
                )
            sources = {
                item.source.strip().casefold(): item.source.strip()
                for item in items
            }
            if len(sources) > 1:
                issues.append(
                    CatalogFeedIssue(
                        1,
                        "source",
                        "snapshot must contain exactly one source",
                    )
                )
            elif len(sources) == 1:
                snapshot_source = next(iter(sources.values()))

        invalid_records = len({issue.record for issue in issues})
        reject_actions = bool(issues) and (snapshot or not allow_partial)
        if reject_actions:
            return CatalogFeedImportReport(
                status="dry_run" if dry_run else "rejected",
                dry_run=dry_run,
                total_records=total_records,
                valid_records=len(items),
                invalid_records=invalid_records,
                issues=tuple(issues),
            )

        ingest_report = (
            self._simulate(items, snapshot_source=snapshot_source)
            if dry_run
            else self._import(items, snapshot_source=snapshot_source)
        )
        return CatalogFeedImportReport(
            status="dry_run" if dry_run else "imported",
            dry_run=dry_run,
            total_records=total_records,
            valid_records=len(items),
            invalid_records=invalid_records,
            created_products=ingest_report.created_products,
            merged_offers=ingest_report.merged_offers,
            updated_offers=ingest_report.updated_offers,
            deactivated_offers=ingest_report.deactivated_offers,
            product_keys=ingest_report.product_keys,
            issues=tuple(issues),
        )

    def _import(
        self,
        items,
        *,
        snapshot_source: str | None,
    ) -> CatalogIngestReport:
        if not items:
            return self._empty_report()
        return self._catalog_service.ingest_external_items_with_report(
            items,
            deactivate_missing_source=snapshot_source,
        )

    def _simulate(
        self,
        items,
        *,
        snapshot_source: str | None,
    ) -> CatalogIngestReport:
        catalog = MasterCatalog()
        catalog.restore(deepcopy(self._catalog_service.catalog.products))
        service = CatalogService(
            catalog=catalog,
            restore_on_start=False,
        )
        return service.ingest_external_items_with_report(
            items,
            deactivate_missing_source=snapshot_source,
        )

    def _decode_records(
        self,
        text: str,
        *,
        format_hint: str | None,
    ) -> tuple[
        list[tuple[int, dict[str, Any]]],
        list[CatalogFeedIssue],
        int,
    ]:
        stripped = text.strip()
        if not stripped:
            return [], [], 0

        hint = (format_hint or "auto").strip().casefold()
        if hint not in {"auto", "json", "jsonl", "ndjson"}:
            return [], [CatalogFeedIssue(1, "format", "unsupported format")], 1

        if hint == "auto":
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                hint = "jsonl"
            else:
                return self._records_from_json(payload)

        if hint == "json":
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as error:
                issue = CatalogFeedIssue(error.lineno, "json", error.msg)
                return [], [issue], 1
            return self._records_from_json(payload)

        return self._records_from_jsonl(text)

    @staticmethod
    def _records_from_json(payload: Any):
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            payload = payload["items"]
        elif isinstance(payload, dict):
            payload = [payload]

        if not isinstance(payload, list):
            issue = CatalogFeedIssue(
                1,
                "json",
                "feed must contain an object or list",
            )
            return [], [issue], 1

        records = []
        issues = []
        for index, value in enumerate(payload, start=1):
            if isinstance(value, dict):
                records.append((index, value))
            else:
                issues.append(
                    CatalogFeedIssue(index, "record", "record must be an object")
                )
        return records, issues, len(payload)

    @staticmethod
    def _records_from_jsonl(text: str):
        records = []
        issues = []
        total = 0
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            total += 1
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                issues.append(
                    CatalogFeedIssue(line_number, "json", error.msg)
                )
                continue
            if isinstance(value, dict):
                records.append((line_number, value))
            else:
                issues.append(
                    CatalogFeedIssue(
                        line_number,
                        "record",
                        "record must be an object",
                    )
                )
        return records, issues, total

    @staticmethod
    def _empty_report() -> CatalogIngestReport:
        return CatalogIngestReport(
            total_offers=0,
            created_products=0,
            merged_offers=0,
            updated_offers=0,
        )

    @staticmethod
    def _format_from_suffix(suffix: str) -> str:
        return (
            "jsonl"
            if suffix.casefold() in {".jsonl", ".ndjson"}
            else "json"
        )
