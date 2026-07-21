from __future__ import annotations

import re
from pathlib import Path


path = Path("app/handlers/search.py")
text = path.read_text(encoding="utf-8")

# Remove repeated hardening imports left by older migrations.
repeated_import = '''from app.services.search_input import SearchInputError, normalize_search_query
from app.services.search_load import (
    SearchBusyError,
    SearchRequestCoordinator,
)
from app.services.search_sessions import (
    SearchSessionRegistry,
    SelectionQueryRegistry,
)
'''
first = text.find(repeated_import)
if first >= 0:
    tail = text[first + len(repeated_import):]
    tail = tail.replace(repeated_import, "")
    text = text[: first + len(repeated_import)] + tail

selection_import = '''from app.services.selection_flow import (
    ordered_memory_groups,
    ordered_variant_groups,
)
'''
anchor = 'from app.services.search_sessions import (\n    SearchSessionRegistry,\n    SelectionQueryRegistry,\n)\n'
if selection_import not in text:
    text = text.replace(anchor, anchor + selection_import, 1)

# All model indexes must use the same reverse order in rendering and callbacks.
text = text.replace(
    "group_model_variants(products)",
    "ordered_variant_groups(products, group_model_variants)",
)
text = text.replace(
    "group_by_memory(\n            group.products\n        )",
    "ordered_memory_groups(group.products)",
)

old_variant = '''    user_id = callback_user_id(callback)
    original_query = selection_query_registry.get(
        chat_id=message_chat_id(callback.message),
        user_id=user_id,
        product_key=group.products[0].key,
    )
    await show_color_selection(
        message=callback.message,
        group=group,
        products=group.products,
        back_callback=(
            f"olp:{search_id}:"
            f"{group_index // PRODUCT_PAGE_SIZE}"
        ),
        original_query=original_query,
        user_id=user_id,
    )
'''
new_variant = '''    memory_groups = ordered_memory_groups(group.products)
    await callback.message.edit_text(
        f"📱 {group.title}\\n\\nВыбери память:",
        reply_markup=build_memory_keyboard(
            search_id=search_id,
            group_index=group_index,
            memory_groups=memory_groups,
        ),
    )
'''
if old_variant not in text:
    raise RuntimeError("variant handler target not found")
text = text.replace(old_variant, new_variant, 1)

old_memory_show = '''    await show_color_selection(
        message=callback.message,
        group=group,
        products=memory_products,
        back_callback=(
            f"olg:{search_id}:{group_index}"
        ),
        original_query=original_query,
        user_id=user_id,
    )
'''
new_memory_show = '''    await show_color_selection(
        message=callback.message,
        group=group,
        products=memory_products,
        back_callback=f"olg:{search_id}:{group_index}",
        any_callback=(
            f"ola:{search_id}:{group_index}:{memory_index}"
        ),
        original_query=original_query,
        user_id=user_id,
    )
'''
if old_memory_show not in text:
    raise RuntimeError("memory handler target not found")
text = text.replace(old_memory_show, new_memory_show, 1)

# Device selection must always go to memory, even for a single variant.
shortcut = '''        if (
            len(group.products) == 1
            and requested_color_key(group.products[0].title) is None
        ):
            callback_data = (
                f"ol:{group.products[0].key}"
            )
        else:
            callback_data = (
                f"olg:{search_id}:{group_index}"
            )
'''
replacement = '''        callback_data = f"olg:{search_id}:{group_index}"
'''
if shortcut not in text:
    raise RuntimeError("product shortcut target not found")
text = text.replace(shortcut, replacement, 1)

text = text.replace(
    '''    back_callback: str,
    original_query: str | None = None,
''',
    '''    back_callback: str,
    any_callback: str,
    original_query: str | None = None,
''',
    1,
)
text = text.replace(
    '''    builder = InlineKeyboardBuilder()
    sorted_choices = sorted(
''',
    '''    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🎨 Любой — найти дешевле",
            callback_data=any_callback,
        )
    )
    sorted_choices = sorted(
''',
    1,
)
text = text.replace(
    '''        f"📱 {group.title}\\n\\n"
        "Выбери цвет. Если у цвета несколько вариантов памяти, "
        "она указана в кнопке:",
''',
    '''        f"📱 {group.title}\\n\\n"
        "Выбери цвет или нажми «Любой», чтобы найти "
        "самую низкую цену среди всех цветов выбранной памяти:",
''',
    1,
)

any_handler = r'''

@router.callback_query(F.data.startswith("ola:"))
async def handle_any_color_selection(callback: CallbackQuery) -> None:
    """Ищет минимальную цену среди всех цветов выбранной памяти."""

    await callback.answer()
    if callback.message is None:
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return

    _, search_id, raw_group_index, raw_memory_index = parts
    products = authorized_product_search(callback, search_id)
    if products is None:
        await callback.message.edit_text(
            "Результаты поиска устарели. Повтори запрос."
        )
        return

    try:
        group_index = int(raw_group_index)
        memory_index = int(raw_memory_index)
        group = ordered_variant_groups(
            products,
            group_model_variants,
        )[group_index]
        memory_products = ordered_memory_groups(
            group.products
        )[memory_index][1]
    except (ValueError, IndexError):
        return

    user_id = callback_user_id(callback)
    original_query = selection_query_registry.get(
        chat_id=message_chat_id(callback.message),
        user_id=user_id,
        product_key=memory_products[0].key,
    )
    await load_any_color_comparison(
        message=callback.message,
        products=memory_products,
        original_query=original_query,
        user_id=user_id,
    )


async def load_any_color_comparison(
    message: Message,
    products: list[ProductCandidate],
    original_query: str | None,
    user_id: int | None,
) -> None:
    """Объединяет предложения всех цветов и сортирует по цене."""

    await message.edit_text(
        "🔎 Ищу минимальную цену среди всех цветов..."
    )

    async def load(product: ProductCandidate) -> ComparisonResult | None:
        try:
            return await price_service.search_all_sources_by_onliner_key(
                product.key,
                original_query=None,
            )
        except (ProductNotFoundError, SourceUnavailableError):
            return None

    try:
        results = await asyncio.gather(*(load(product) for product in products))
    except Exception:
        logger.exception("Unexpected any-color comparison error")
        await message.edit_text("Произошла ошибка при сравнении цветов.")
        return

    successful = [result for result in results if result and result.offers]
    if not successful:
        await message.edit_text("Предложения для выбранной памяти не найдены.")
        return

    unique: dict[tuple[str, str], ProductOffer] = {}
    for result in successful:
        for offer in result.offers:
            unique.setdefault(((offer.seller or "").casefold(), offer.url), offer)
    offers = sorted(unique.values(), key=lambda offer: float(offer.price))
    cheapest_result = min(
        successful,
        key=lambda result: min(float(offer.price) for offer in result.offers),
    )
    comparison = replace(
        cheapest_result,
        offers=offers,
        query=original_query or cheapest_result.query,
    )
    product_key = cheapest_result.product_key or products[0].key

    chat_id = message_chat_id(message)
    if chat_id is not None:
        store_comparison_diagnostics(
            chat_id=chat_id,
            user_id=user_id,
            comparison=comparison,
        )
    try:
        await asyncio.to_thread(
            get_price_history_repository().record_offers,
            product_key,
            comparison.product_title,
            offers,
        )
    except Exception:
        logger.exception("Any-color history write failed")

    await show_comparison(
        message=message,
        offers=offers,
        source_statuses=comparison.source_statuses,
        product_key=product_key,
        product_title=None,
        grouped=False,
    )
'''
marker = '@router.message(Command("five_search"))'
if 'async def handle_any_color_selection' not in text:
    if marker not in text:
        raise RuntimeError("any-color insertion marker not found")
    text = text.replace(marker, any_handler + "\n\n" + marker, 1)

# Collapse duplicated session registration generated by old migrations.
pattern = re.compile(
    r'(    product_session_registry\.register\(\n'
    r'        search_id,\n'
    r'        query=query,\n'
    r'        owner_chat_id=owner_chat_id,\n'
    r'        owner_user_id=owner_user_id,\n'
    r'    \)\n'
    r'    for product in products:\n'
    r'        selection_query_registry\.remember\(\n'
    r'            chat_id=owner_chat_id,\n'
    r'            user_id=owner_user_id,\n'
    r'            product_key=product\.key,\n'
    r'            query=query,\n'
    r'        \)\n)(?:\1)+',
)
text = pattern.sub(r'\1', text)
text = re.sub(
    r'(        product_session_registry\.remove\(expired_search_id\)\n)(?:\1)+',
    r'\1',
    text,
)

path.write_text(text, encoding="utf-8")
