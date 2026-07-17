import json
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT_DIR),
)

from app.services.five_element_index import (
    FiveElementIndex,
)


QUERY = "iPhone 17 256GB"

INDEX_PATH = Path(
    "data/five_element_index.json"
)

MEMORY_PATTERN = (
    r"\b(\d+)\s*"
    r"(gb|tb|mb|гб|тб|мб)\b"
)

ACCESSORY_MARKERS = {
    "chehol",
    "чехол",
    "chekhol",
    "bamper",
    "case",
    "cover",
    "nakladka",
    "накладка",
    "steklo",
    "стекло",
    "plenka",
    "пленка",
    "zaschit",
    "защит",
    "kabel",
    "кабель",
    "adapter",
    "адаптер",
    "zaryad",
    "заряд",
    "derzhatel",
    "держатель",
    "remeshok",
    "ремешок",
    "ringke",
    "onyx",
    "fusion",
    "magnetic",
    "magnit",
    "магнит",
}


def main() -> None:
    index = FiveElementIndex()

    normalized_query = index._normalize(
        QUERY
    )

    query_tokens = set(
        normalized_query.split()
    )

    query_memory_specs = {
        (
            amount,
            index._normalize_memory_unit(
                unit
            ),
        )
        for amount, unit in re.findall(
            MEMORY_PATTERN,
            normalized_query,
        )
    }

    memory_amounts = {
        amount
        for amount, _ in query_memory_specs
    }

    query_model_numbers = (
        set(
            re.findall(
                r"\d+",
                normalized_query,
            )
        )
        - memory_amounts
    )

    ignored_units = {
        "gb",
        "tb",
        "mb",
        "гб",
        "тб",
        "мб",
    }

    query_words = {
        token
        for token in query_tokens
        if (
            token.isalpha()
            and token not in ignored_units
        )
    }

    print("ДАННЫЕ ЗАПРОСА")
    print("-" * 70)
    print(
        "Исходный запрос:",
        QUERY,
    )
    print(
        "Нормализованный запрос:",
        normalized_query,
    )
    print(
        "Слова:",
        query_words,
    )
    print(
        "Номер модели:",
        query_model_numbers,
    )
    print(
        "Память:",
        query_memory_specs,
    )
    print()

    data = json.loads(
        INDEX_PATH.read_text(
            encoding="utf-8"
        )
    )

    products = data.get(
        "products",
        []
    )

    found_count = 0

    for product in products:
        title = product.get(
            "title",
            "",
        )

        url = product.get(
            "url",
            "",
        )

        search_value = (
            f"{title} {url}"
        )

        normalized_product = (
            index._normalize(
                search_value
            )
        )

        numbers = set(
            re.findall(
                r"\d+",
                normalized_product,
            )
        )

        if (
            "iphone"
            not in normalized_product
        ):
            continue

        if "17" not in numbers:
            continue

        found_count += 1

        product_tokens = set(
            normalized_product.split()
        )

        product_memory_specs = {
            (
                amount,
                index._normalize_memory_unit(
                    unit
                ),
            )
            for amount, unit in re.findall(
                MEMORY_PATTERN,
                normalized_product,
            )
        }

        accessory_hits = {
            marker
            for marker in ACCESSORY_MARKERS
            if marker in normalized_product
        }

        matching_words = {
            word
            for word in query_words
            if (
                word in product_tokens
                or word in normalized_product
            )
        }

        reasons: list[str] = []

        if accessory_hits:
            reasons.append(
                "ОТБРАСЫВАЕТСЯ КАК АКСЕССУАР"
            )

        if not query_model_numbers.issubset(
            numbers
        ):
            reasons.append(
                "НЕ СОВПАЛ НОМЕР МОДЕЛИ"
            )

        if not query_memory_specs.issubset(
            product_memory_specs
        ):
            reasons.append(
                "НЕ СОВПАЛА ПАМЯТЬ"
            )

        if (
            query_words
            and not matching_words
        ):
            reasons.append(
                "НЕ СОВПАЛО НАЗВАНИЕ"
            )

        if not reasons:
            reasons.append(
                "ДОЛЖЕН ПРОХОДИТЬ ПОИСК"
            )

        print("=" * 70)
        print(
            "TITLE:",
            title,
        )
        print(
            "URL:",
            url,
        )
        print(
            "NORMALIZED:",
            normalized_product,
        )
        print(
            "NUMBERS:",
            numbers,
        )
        print(
            "MEMORY:",
            product_memory_specs,
        )
        print(
            "MATCHING WORDS:",
            matching_words,
        )
        print(
            "ACCESSORY HITS:",
            accessory_hits,
        )
        print(
            "РЕЗУЛЬТАТ:",
            ", ".join(reasons),
        )

        if found_count >= 20:
            break

    print()
    print("-" * 70)
    print(
        "Проверено карточек iPhone 17:",
        found_count,
    )

    actual_results = index.find_products(
        QUERY,
        limit=10,
    )

    print(
        "Метод find_products вернул:",
        len(actual_results),
    )


if __name__ == "__main__":
    main()