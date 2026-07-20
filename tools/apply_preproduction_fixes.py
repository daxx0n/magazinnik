from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f"Missing replacement target: {label}")


def patch_catalog_service() -> None:
    path = ROOT / "app/services/catalog_service.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "    @synchronized\n    async def ingest_offers_with_report_async(\n",
        "    async def ingest_offers_with_report_async(\n",
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_price_history() -> None:
    path = ROOT / "app/services/price_history.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "        with self._connect() as connection:\n            existing = connection.execute(\n",
        "        with self._connect() as connection:\n            connection.execute(\"BEGIN IMMEDIATE\")\n            existing = connection.execute(\n",
        "serialized alert toggle",
    )
    path.write_text(text, encoding="utf-8")


def patch_search_handler() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass, replace\n",
        "dataclass replace import",
    )
    text = replace_once(
        text,
        "] = SearchRequestCoordinator()\n\n\ndef initialize_price_history",
        "] = SearchRequestCoordinator()\ncategory_discovery_coordinator: SearchRequestCoordinator[\n    str,\n    list[ProductCategory],\n] = SearchRequestCoordinator()\nproduct_discovery_coordinator: SearchRequestCoordinator[\n    tuple[str, str],\n    list[ProductCandidate],\n] = SearchRequestCoordinator()\n\n\ndef initialize_price_history",
        "discovery coordinators",
    )
    misplaced_busy = '''    except SearchBusyError:\n        await message.edit_text(\n            "Сейчас выполняется слишком много сравнений. "\n            "Попробуй ещё раз через несколько секунд."\n        )\n        return\n'''
    text = text.replace(misplaced_busy, "", 1)
    text = replace_once(
        text,
        "    async def load_product_comparison(\n",
        "    async def load_product_comparison(\n",
        "noop",
    ) if False else text
    text = replace_once(
        text,
        "async def load_product_comparison(\n    message: Message,\n    product_key: str,\n    original_query: str | None = None,\n) -> None:\n",
        "async def load_product_comparison(\n    message: Message,\n    product_key: str,\n    original_query: str | None = None,\n    user_id: int | None = None,\n) -> None:\n",
        "comparison user signature",
    )
    text = replace_once(
        text,
        "        comparison = await comparison_coordinator.run(\n            (product_key, original_query or \"\"),\n            lambda: price_service.search_all_sources_by_onliner_key(\n                product_key,\n                original_query=original_query,\n            ),\n        )\n",
        "        comparison = await comparison_coordinator.run(\n            (product_key, \"\"),\n            lambda: price_service.search_all_sources_by_onliner_key(\n                product_key,\n                original_query=None,\n            ),\n        )\n        if original_query:\n            comparison = replace(\n                comparison,\n                query=original_query,\n            )\n",
        "coalesce product comparison",
    )
    text = replace_once(
        text,
        "    except ProductNotFoundError as error:\n        await message.edit_text(\n            f\"Предложения не найдены.\\n\\n{error}\"\n        )\n",
        "    except SearchBusyError:\n        await message.edit_text(\n            \"Сейчас выполняется слишком много сравнений. \"\n            \"Попробуй ещё раз через несколько секунд.\"\n        )\n        return\n    except ProductNotFoundError as error:\n        await message.edit_text(\n            f\"Предложения не найдены.\\n\\n{error}\"\n        )\n",
        "comparison busy response",
    )
    text = replace_once(
        text,
        "            user_id=message_user_id(message),\n            comparison=comparison,\n",
        "            user_id=user_id,\n            comparison=comparison,\n",
        "explicit diagnostics user",
    )
    text = replace_once(
        text,
        "        original_query=original_query,\n    )\n\n\nasync def load_product_comparison",
        "        original_query=original_query,\n        user_id=user_id,\n    )\n\n\nasync def load_product_comparison",
        "selection user passthrough",
    )
    text = replace_once(
        text,
        "async def show_color_selection(\n    message: Message,\n    group: ProductVariantGroup,\n    products: list[ProductCandidate],\n    back_callback: str,\n) -> None:\n",
        "async def show_color_selection(\n    message: Message,\n    group: ProductVariantGroup,\n    products: list[ProductCandidate],\n    back_callback: str,\n    original_query: str | None = None,\n    user_id: int | None = None,\n) -> None:\n",
        "color selection context signature",
    )
    text = replace_once(
        text,
        "                product_key=only_product.key,\n            )\n",
        "                product_key=only_product.key,\n                original_query=original_query,\n                user_id=user_id,\n            )\n",
        "automatic selection context",
    )
    old_variant_call = '''    await show_color_selection(\n        message=callback.message,\n        group=group,\n        products=group.products,\n        back_callback=(\n            f"olp:{search_id}:"\n            f"{group_index // PRODUCT_PAGE_SIZE}"\n        ),\n    )\n'''
    new_variant_call = '''    user_id = callback_user_id(callback)\n    original_query = selection_query_registry.get(\n        chat_id=message_chat_id(callback.message),\n        user_id=user_id,\n        product_key=group.products[0].key,\n    )\n    await show_color_selection(\n        message=callback.message,\n        group=group,\n        products=group.products,\n        back_callback=(\n            f"olp:{search_id}:"\n            f"{group_index // PRODUCT_PAGE_SIZE}"\n        ),\n        original_query=original_query,\n        user_id=user_id,\n    )\n'''
    text = replace_once(text, old_variant_call, new_variant_call, "variant context")
    old_memory_call = '''    await show_color_selection(\n        message=callback.message,\n        group=group,\n        products=memory_products,\n        back_callback=(\n            f"olg:{search_id}:{group_index}"\n        ),\n    )\n'''
    new_memory_call = '''    user_id = callback_user_id(callback)\n    original_query = selection_query_registry.get(\n        chat_id=message_chat_id(callback.message),\n        user_id=user_id,\n        product_key=memory_products[0].key,\n    )\n    await show_color_selection(\n        message=callback.message,\n        group=group,\n        products=memory_products,\n        back_callback=(\n            f"olg:{search_id}:{group_index}"\n        ),\n        original_query=original_query,\n        user_id=user_id,\n    )\n'''
    text = replace_once(text, old_memory_call, new_memory_call, "memory context")
    text = replace_once(
        text,
        "                await price_service.find_onliner_categories(query)\n",
        "                await category_discovery_coordinator.run(\n                    query.casefold(),\n                    lambda: price_service.find_onliner_categories(query),\n                )\n",
        "category discovery coordination",
    )
    old_product_search = '''        products = (\n            await price_service\n            .find_onliner_products(\n                query,\n                category=(\n                    categories[0].key\n                    if len(categories) == 1\n                    else None\n                ),\n            )\n        )\n'''
    new_product_search = '''        selected_category = (\n            categories[0].key\n            if len(categories) == 1\n            else None\n        )\n        products = await product_discovery_coordinator.run(\n            (query.casefold(), selected_category or ""),\n            lambda: price_service.find_onliner_products(\n                query,\n                category=selected_category,\n            ),\n        )\n'''
    text = replace_once(text, old_product_search, new_product_search, "product discovery")
    text = replace_once(
        text,
        "    except SourceUnavailableError as error:\n        logger.warning(\n            \"Onliner search unavailable: %s\",\n",
        "    except SearchBusyError:\n        await status_message.edit_text(\n            \"Сейчас выполняется слишком много поисков. \"\n            \"Попробуй ещё раз через несколько секунд.\"\n        )\n        return\n    except SourceUnavailableError as error:\n        logger.warning(\n            \"Onliner search unavailable: %s\",\n",
        "search busy response",
    )
    text = replace_once(
        text,
        "        products = await price_service.find_onliner_products(\n            query=session.query,\n            category=category.key,\n        )\n",
        "        products = await product_discovery_coordinator.run(\n            (session.query.casefold(), category.key),\n            lambda: price_service.find_onliner_products(\n                query=session.query,\n                category=category.key,\n            ),\n        )\n",
        "category product coordination",
    )
    text = replace_once(
        text,
        "    except SourceUnavailableError as error:\n        logger.warning(\n            \"Onliner category search unavailable: %s\",\n",
        "    except SearchBusyError:\n        await callback.message.edit_text(\n            \"Сейчас выполняется слишком много поисков. \"\n            \"Попробуй ещё раз через несколько секунд.\"\n        )\n        return\n    except SourceUnavailableError as error:\n        logger.warning(\n            \"Onliner category search unavailable: %s\",\n",
        "category busy response",
    )
    text = replace_once(
        text,
        "    query = command_parts[1].strip()\n\n    status_message = await message.answer(\n",
        "    try:\n        query = normalize_search_query(command_parts[1])\n    except SearchInputError as error:\n        await message.answer(str(error))\n        return\n\n    status_message = await message.answer(\n",
        "five search normalization",
    )
    old_product_auth = '''    if metadata is None or products is None:\n        if products is None:\n            product_session_registry.remove(search_id)\n        return None\n'''
    new_product_auth = '''    if metadata is None or products is None:\n        product_searches.pop(search_id, None)\n        product_search_parents.pop(search_id, None)\n        product_session_registry.remove(search_id)\n        return None\n'''
    text = replace_once(text, old_product_auth, new_product_auth, "product cleanup")
    old_category_auth = '''    if metadata is None or session is None:\n        if session is None:\n            category_session_registry.remove(search_id)\n        return None\n'''
    new_category_auth = '''    if metadata is None or session is None:\n        category_searches.pop(search_id, None)\n        category_session_registry.remove(search_id)\n        return None\n'''
    text = replace_once(text, old_category_auth, new_category_auth, "category cleanup")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_catalog_service()
    patch_price_history()
    patch_search_handler()


if __name__ == "__main__":
    main()
