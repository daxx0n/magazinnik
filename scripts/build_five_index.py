import asyncio
import sys
from pathlib import Path


ROOT_DIR = Path(
    __file__
).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT_DIR),
)

from app.services.five_element_index import (
    FiveElementIndex,
)


async def main() -> None:
    """Создаёт локальный индекс 5 элемента."""

    index = FiveElementIndex()

    count = await index.rebuild()

    print(
        "Индекс 5 элемента создан: "
        f"{count} товаров."
    )


if __name__ == "__main__":
    asyncio.run(main())