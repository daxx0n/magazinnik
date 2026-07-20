import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.services.catalog_feed_import import CatalogFeedImporter
from app.services.catalog_service import CatalogService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import JSON or JSONL products into the master catalog.",
    )
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--format",
        choices=("auto", "json", "jsonl", "ndjson"),
        default="auto",
    )
    parser.add_argument("--source", dest="default_source")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    report = CatalogFeedImporter(CatalogService()).import_file(
        args.path,
        dry_run=args.dry_run,
        allow_partial=args.allow_partial,
        default_source=args.default_source,
        format_hint=args.format,
    )
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    if report.status == "rejected":
        return 2
    if report.invalid_records:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
