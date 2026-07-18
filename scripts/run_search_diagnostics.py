"""Проверяет сквозной поиск и сохраняет JSON-отчёт."""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT_DIR),
)

from app.services.price_service import PriceService


DEFAULT_QUERIES = [
    "Bosch HBA534EB3",
    "Samsung UE55DU7100UXRU",
    "LG OLED55C4RLA",
    "Apple iPhone 16 Pro 256GB",
    "Samsung Galaxy S24 Ultra 256GB",
    "Apple MacBook Air M3 256GB",
    "Samsung SM-A556E 256GB",
    "Xiaomi Redmi Note 13 Pro 256GB",
    "Apple AirPods Pro 2",
    "Roborock Q8 Max",
    "Dyson V15 Detect",
    "LG GC-B509SECL",
    "Bosch SMS4HMI07E",
    "DeLonghi ECAM 22.110.B",
    "Sony PlayStation 5 Slim",
    "Apple iPhone 17 Pro 256GB",
    "Samsung Galaxy S25 Ultra 256GB",
    "Xiaomi 14T Pro 512GB",
    "Google Pixel 9 Pro 256GB",
    "Huawei Pura 70 Pro 512GB",
    "Lenovo LOQ 15IRX9",
    "ASUS TUF Gaming A15 FA507NV",
    "TCL 55C755",
    "Samsung WW90T554CAT",
    "Sony WH-1000XM5",
    "JBL Flip 6",
    "Microsoft Xbox Series X",
    "Nintendo Switch OLED",
    "Oral-B iO 6",
    "Apple Watch Series 10 GPS 46mm",
    "Samsung Galaxy Tab S10 256GB Wi-Fi",
    "Garmin Forerunner 965",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Прогоняет поиск по пяти источникам "
            "и сохраняет диагностический отчёт."
        )
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help=(
            "Товар для проверки. Параметр можно "
            "повторить несколько раз."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Путь итогового JSON-файла.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Пауза между товарами в секундах.",
    )
    return parser.parse_args()


async def diagnose_query(
    service: PriceService,
    query: str,
) -> dict[str, object]:
    started_at = time.perf_counter()
    result: dict[str, object] = {
        "query": query,
        "onliner_candidates": [],
        "selected_product": None,
        "offers": [],
        "source_statuses": [],
        "match_decisions": [],
        "error": None,
    }

    try:
        products = await service.find_onliner_products(
            query
        )
        result["onliner_candidates"] = [
            asdict(product)
            for product in products
        ]

        if not products:
            result["error"] = (
                "Onliner не нашёл кандидатов."
            )
            return result

        # Как и пользователь в Telegram, выбираем карточку
        # модели. Для автоматического прогона берём первый
        # результат и сохраняем весь список для проверки.
        selected_product = products[0]
        result["selected_product"] = asdict(
            selected_product
        )

        comparison = (
            await service
            .search_all_sources_by_onliner_key(
                selected_product.key
            )
        )
        result["offers"] = [
            asdict(offer)
            for offer in comparison.offers
        ]
        result["source_statuses"] = [
            asdict(status)
            for status in comparison.source_statuses
        ]
        result["match_decisions"] = [
            asdict(decision)
            for decision in comparison.match_decisions
        ]
    except Exception as error:
        result["error"] = (
            f"{type(error).__name__}: {error}"
        )
    finally:
        result["duration_seconds"] = round(
            time.perf_counter() - started_at,
            3,
        )

    return result


async def run(
    queries: list[str],
    output_path: Path,
    delay: float,
) -> None:
    service = PriceService()
    results: list[dict[str, object]] = []

    for position, query in enumerate(
        queries,
        start=1,
    ):
        print(
            f"[{position}/{len(queries)}] {query}"
        )
        result = await diagnose_query(
            service,
            query,
        )
        results.append(result)

        statuses = result["source_statuses"]
        error = result["error"]

        if error:
            print(f"  Ошибка: {error}")
        else:
            summary = ", ".join(
                f"{status['source']}={status['state']}"
                for status in statuses
            )
            print(f"  {summary}")

        if position < len(queries) and delay > 0:
            await asyncio.sleep(delay)

    payload = {
        "generated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "query_count": len(queries),
        "results": results,
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nОтчёт сохранён: {output_path}")


def main() -> None:
    args = parse_args()
    queries = args.queries or DEFAULT_QUERIES
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    output_path = args.output or Path(
        "data",
        f"search_diagnostics_{timestamp}.json",
    )

    asyncio.run(
        run(
            queries=queries,
            output_path=output_path,
            delay=max(args.delay, 0),
        )
    )


if __name__ == "__main__":
    main()
