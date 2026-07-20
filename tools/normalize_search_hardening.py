from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text(encoding="utf-8")

    registry_pattern = re.compile(
        r"product_session_registry = SearchSessionRegistry\(.*?"
        r"(?=\n\n\ndef initialize_price_history\()",
        re.DOTALL,
    )
    registry_block = '''product_session_registry = SearchSessionRegistry(
    capacity=MAX_SEARCH_SESSIONS,
    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,
)
category_session_registry = SearchSessionRegistry(
    capacity=MAX_SEARCH_SESSIONS,
    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,
)
selection_query_registry = SelectionQueryRegistry(
    capacity=10_000,
    ttl_seconds=SEARCH_SESSION_TTL_SECONDS,
)
comparison_coordinator: SearchRequestCoordinator[
    tuple[str, str],
    ComparisonResult,
] = SearchRequestCoordinator()
category_discovery_coordinator: SearchRequestCoordinator[
    str,
    list[ProductCategory],
] = SearchRequestCoordinator()
product_discovery_coordinator: SearchRequestCoordinator[
    tuple[str, str],
    list[ProductCandidate],
] = SearchRequestCoordinator()
'''
    text, count = registry_pattern.subn(registry_block, text, count=1)
    if count != 1:
        raise RuntimeError("Unable to normalize search registries")

    busy_block = '''    except SearchBusyError:
        await message.edit_text(
            "Сейчас выполняется слишком много сравнений. "
            "Попробуй ещё раз через несколько секунд."
        )
        return
'''
    while busy_block + busy_block in text:
        text = text.replace(busy_block + busy_block, busy_block)

    search_busy = '''    except SearchBusyError:
        await status_message.edit_text(
            "Сейчас выполняется слишком много поисков. "
            "Попробуй ещё раз через несколько секунд."
        )
        return
'''
    while search_busy + search_busy in text:
        text = text.replace(search_busy + search_busy, search_busy)

    category_busy = '''    except SearchBusyError:
        await callback.message.edit_text(
            "Сейчас выполняется слишком много поисков. "
            "Попробуй ещё раз через несколько секунд."
        )
        return
'''
    while category_busy + category_busy in text:
        text = text.replace(category_busy + category_busy, category_busy)

    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
