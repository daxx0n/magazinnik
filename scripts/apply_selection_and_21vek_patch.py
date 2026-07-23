from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_section(text: str, start: str, end: str, replacement: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"Start marker not found: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"End marker not found: {end!r}")
    return text[:start_index] + replacement.rstrip() + "\n\n" + text[end_index:]


def remove_updated_offer_block(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    index = 0
    removed = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("if offer.updated_at"):
            indent = len(line) - len(line.lstrip())
            block = [line]
            cursor = index + 1
            while cursor < len(lines):
                candidate = lines[cursor]
                if not candidate.strip():
                    block.append(candidate)
                    cursor += 1
                    continue
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate_indent <= indent:
                    break
                block.append(candidate)
                cursor += 1
            if any("Обновлено" in item for item in block):
                removed += 1
                index = cursor
                continue
        result.append(line)
        index += 1

    if removed == 0 and "🕒 Обновлено:" in text:
        raise RuntimeError("Could not remove the updated-at presentation block")
    return "\n".join(result) + ("\n" if text.endswith("\n") else "")


def patch_selection_flow() -> None:
    path = ROOT / "app/services/selection_flow.py"
    text = path.read_text()
    if "def selectable_memory_groups(" in text:
        return

    addition = '''\n\ndef selectable_memory_groups(\n    products: Iterable[ProductCandidate],\n) -> list[tuple[str, list[ProductCandidate]]]:\n    """Returns only explicit memory variants suitable for user selection."""\n\n    return [\n        group\n        for group in ordered_memory_groups(products)\n        if group[0] != "Без выбора"\n    ]\n\n\ndef has_memory_choice(\n    products: Iterable[ProductCandidate],\n) -> bool:\n    """True only when a model has at least two explicit memory variants."""\n\n    return len(selectable_memory_groups(products)) > 1\n'''
    path.write_text(text.rstrip() + addition + "\n")


def patch_search_handler() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text()

    old_import = '''from app.services.selection_flow import (\n    ordered_memory_groups,\n    ordered_variant_groups,\n)'''
    new_import = '''from app.services.selection_flow import (\n    has_memory_choice,\n    ordered_memory_groups,\n    ordered_variant_groups,\n    selectable_memory_groups,\n)'''
    if old_import in text:
        text = text.replace(old_import, new_import, 1)
    elif "selectable_memory_groups" not in text:
        raise RuntimeError("selection_flow import block was not found")

    variant_handler = '''@router.callback_query(\n    F.data.startswith("olg:")\n)\nasync def handle_variant_group(\n    callback: CallbackQuery,\n) -> None:\n    """Shows memory only when the selected model has real memory variants."""\n\n    await callback.answer()\n\n    if callback.message is None:\n        return\n\n    parts = (callback.data or "").split(":")\n\n    if len(parts) != 3:\n        return\n\n    _, search_id, raw_group_index = parts\n    products = authorized_product_search(callback, search_id)\n\n    if products is None:\n        await callback.message.edit_text(\n            "Результаты поиска устарели. "\n            "Повтори запрос."\n        )\n        return\n\n    try:\n        group_index = int(raw_group_index)\n        group = ordered_variant_groups(products, group_model_variants)[\n            group_index\n        ]\n    except (ValueError, IndexError):\n        return\n\n    if not group.products:\n        return\n\n    if not has_memory_choice(group.products):\n        user_id = callback_user_id(callback)\n        original_query = selection_query_registry.get(\n            chat_id=message_chat_id(callback.message),\n            user_id=user_id,\n            product_key=group.products[0].key,\n        )\n        await show_color_selection(\n            message=callback.message,\n            group=group,\n            products=group.products,\n            back_callback=(\n                f"olp:{search_id}:"\n                f"{group_index // PRODUCT_PAGE_SIZE}"\n            ),\n            any_callback=f"ola:{search_id}:{group_index}:all",\n            original_query=original_query,\n            user_id=user_id,\n            memory_selected=False,\n        )\n        return\n\n    memory_groups = selectable_memory_groups(group.products)\n    await callback.message.edit_text(\n        f"🏷️ {group.title}\\n\\nВыбери память:",\n        reply_markup=build_memory_keyboard(\n            search_id=search_id,\n            group_index=group_index,\n            memory_groups=memory_groups,\n        ),\n    )'''
    if "memory_selected=False" not in text:
        text = replace_section(
            text,
            '@router.callback_query(\n    F.data.startswith("olg:")\n)\nasync def handle_variant_group(',
            '@router.callback_query(\n    F.data.startswith("olm:")\n)',
            variant_handler,
        )

    text = text.replace(
        "ordered_memory_groups(group.products)[memory_index][1]",
        "selectable_memory_groups(group.products)[memory_index][1]",
    )

    any_handler = '''@router.callback_query(F.data.startswith("ola:"))\nasync def handle_any_color_selection(callback: CallbackQuery) -> None:\n    """Searches the lowest price among all colors of the selected variant."""\n\n    await callback.answer()\n    if callback.message is None:\n        return\n\n    parts = (callback.data or "").split(":")\n    if len(parts) != 4:\n        return\n\n\n    _, search_id, raw_group_index, raw_memory_index = parts\n    products = authorized_product_search(callback, search_id)\n    if products is None:\n        await callback.message.edit_text(\n            "Результаты поиска устарели. Повтори запрос."\n        )\n        return\n\n\n    try:\n        group_index = int(raw_group_index)\n        group = ordered_variant_groups(\n            products,\n            group_model_variants,\n        )[group_index]\n        if raw_memory_index == "all":\n            memory_products = group.products\n        else:\n            memory_index = int(raw_memory_index)\n            memory_products = selectable_memory_groups(\n                group.products\n            )[memory_index][1]\n    except (ValueError, IndexError):\n        return\n\n    if not memory_products:\n        return\n\n    user_id = callback_user_id(callback)\n    original_query = selection_query_registry.get(\n        chat_id=message_chat_id(callback.message),\n        user_id=user_id,\n        product_key=memory_products[0].key,\n    )\n    await load_any_color_comparison(\n        message=callback.message,\n        products=memory_products,\n        original_query=original_query,\n        user_id=user_id,\n    )'''
    if 'raw_memory_index == "all"' not in text:
        text = replace_section(
            text,
            '@router.callback_query(F.data.startswith("ola:"))',
            'async def load_any_color_comparison(',
            any_handler,
        )

    color_selection = '''async def show_color_selection(\n    message: Message,\n    group: ProductVariantGroup,\n    products: list[ProductCandidate],\n    back_callback: str,\n    any_callback: str | None = None,\n    original_query: str | None = None,\n    user_id: int | None = None,\n    memory_selected: bool = True,\n) -> None:\n    """Shows color choices and skips memory wording when memory is not selectable."""\n\n    colored_products = [\n        product\n        for product in products\n        if requested_color_key(product.title) is not None\n    ]\n    selectable_products = colored_products or products\n\n    choices: dict[tuple[str, str], ProductCandidate] = {}\n    for product in selectable_products:\n        color_key = requested_color_key(product.title) or "unknown"\n        memory = extract_memory(product.title) or "Без выбора памяти"\n        choice_memory = memory if memory_selected else ""\n        choices.setdefault((color_key, choice_memory), product)\n\n    if len(choices) == 1:\n        only_product = next(iter(choices.values()))\n        if requested_color_key(only_product.title) is None:\n            await load_product_comparison(\n                message=message,\n                product_key=only_product.key,\n                original_query=original_query,\n                user_id=user_id,\n            )\n            return\n\n    color_counts = Counter(\n        color_key for color_key, _ in choices\n    )\n    builder = InlineKeyboardBuilder()\n    if any_callback is not None:\n        builder.row(\n            InlineKeyboardButton(\n                text="🎨 Любой — найти дешевле",\n                callback_data=any_callback,\n            )\n        )\n    sorted_choices = sorted(\n        choices.items(),\n        key=lambda item: (\n            (selected_color_label(item[1].title) or "").casefold(),\n            item[0][1],\n            item[1].title.casefold(),\n        ),\n    )\n\n    for (color_key, memory), product in sorted_choices:\n        label = selected_color_label(product.title) or "Цвет не указан"\n        if memory_selected and color_counts[color_key] > 1:\n            label = f"{label} · {memory}"\n\n        builder.row(\n            InlineKeyboardButton(\n                text=(\n                    label\n                    if len(label) <= 58\n                    else label[:55] + "..."\n                ),\n                callback_data=f"ol:{product.key}",\n            )\n        )\n\n    builder.row(\n        InlineKeyboardButton(\n            text="⬅️ Назад",\n            callback_data=back_callback,\n        )\n    )\n\n    if any_callback is None:\n        prompt = "Выбери цвет:"\n    elif memory_selected:\n        prompt = (\n            "Выбери цвет или нажми «Любой», чтобы найти "\n            "самую низкую цену среди всех цветов выбранной памяти:"\n        )\n    else:\n        prompt = (\n            "Выбери цвет или нажми «Любой», чтобы найти "\n            "самую низкую цену среди всех цветов:"\n        )\n\n    await message.edit_text(\n        f"🏷️ {group.title}\\n\\n{prompt}",\n        reply_markup=builder.as_markup(),\n    )'''
    if "memory_selected: bool = True" not in text:
        text = replace_section(
            text,
            "async def show_color_selection(",
            "def store_product_search(",
            color_selection,
        )

    text = text.replace("📱 ", "🏷️ ")
    text = remove_updated_offer_block(text)
    text = text.replace(
        'await message.edit_text("Предложения для выбранной памяти не найдены.")',
        'await message.edit_text("Предложения для выбранного варианта не найдены.")',
    )
    path.write_text(text)


def patch_twenty_one_vek() -> None:
    path = ROOT / "app/sources/twenty_one_vek.py"
    text = path.read_text()
    if "def _query_variants(" in text:
        return

    text = text.replace("import json\n", "import json\nimport re\n", 1)
    text = text.replace(
        "    async def find_offers(\n",
        "    async def _find_offers_once(\n",
        1,
    )

    marker = "    async def _find_offers_once(\n"
    insert_at = text.find(marker)
    if insert_at < 0:
        raise RuntimeError("TwentyOneVekSource.find_offers was not found")

    wrapper = '''    _query_token_pattern = re.compile(\n        r"(?<![a-zа-я0-9])"\n        r"[a-zа-я0-9]+(?:[-_/.][a-zа-я0-9]+)*"\n        r"(?![a-zа-я0-9])",\n        re.IGNORECASE,\n    )\n    _memory_pair_pattern = re.compile(\n        r"\\d{1,4}\\s*(?:gb|tb|mb|гб|тб|мб)?\\s*[/_-]\\s*"\n        r"\\d{1,4}\\s*(?:gb|tb|mb|гб|тб|мб)?",\n        re.IGNORECASE,\n    )\n    _measurement_pattern = re.compile(\n        r"\\d+(?:gb|tb|mb|гб|тб|мб|hz|khz|mhz|ghz|"\n        r"w|kw|v|mah|mp|g|k)",\n        re.IGNORECASE,\n    )\n    _ignored_identifier_tokens = {\n        "2sim", "3g", "4g", "5g", "4k", "8k", "esim", "lte",\n    }\n    _query_noise_words = {\n        "ai", "lcd", "led", "microled", "miniled", "monitor",\n        "nano", "nanocell", "neoqled", "oled", "qled", "qned",\n        "smart", "television", "tv", "uhd", "монитор", "смарт",\n        "телевизор",\n    }\n\n    @staticmethod\n    def _compact_identifier(value: str) -> str:\n        return re.sub(r"[^a-zа-я0-9]", "", value.casefold())\n\n    @classmethod\n    def _model_query_parts(\n        cls,\n        query: str,\n    ) -> tuple[str | None, list[str], list[str]]:\n        raw_tokens = cls._query_token_pattern.findall(query)\n        brand: str | None = None\n        family: list[str] = []\n        strong: list[str] = []\n\n        for raw_token in raw_tokens:\n            token = raw_token.strip("._/-")\n            compact = cls._compact_identifier(token)\n            if not compact:\n                continue\n\n            if (\n                brand is None\n                and token.isalpha()\n                and compact not in cls._query_noise_words\n                and len(compact) >= 2\n            ):\n                brand = token\n\n            if compact in cls._ignored_identifier_tokens:\n                continue\n            if cls._memory_pair_pattern.fullmatch(token) is not None:\n                continue\n            if cls._measurement_pattern.fullmatch(compact) is not None:\n                continue\n            if re.search(r"[a-zа-я]", compact) is None:\n                continue\n            if re.search(r"\\d", compact) is None:\n                continue\n\n            has_separator = any(character in token for character in "-_/." )\n            numeric_prefix_identifier = (\n                token[0].isdigit()\n                and len(compact) >= 5\n                and sum(character.isdigit() for character in compact) >= 3\n            )\n            alpha_long_identifier = token[0].isalpha() and len(compact) >= 5\n            if has_separator or numeric_prefix_identifier or alpha_long_identifier:\n                strong.append(token)\n\n            if not has_separator and 2 <= len(compact) <= 6:\n                family.append(token)\n\n        strong_compacts = {\n            token: cls._compact_identifier(token) for token in strong\n        }\n        strong = [\n            token\n            for token in strong\n            if not any(\n                strong_compacts[token] != strong_compacts[other]\n                and strong_compacts[token] in strong_compacts[other]\n                for other in strong\n            )\n        ]\n\n        def unique(values: list[str]) -> list[str]:\n            result: list[str] = []\n            seen: set[str] = set()\n            for value in values:\n                key = value.casefold()\n                if key not in seen:\n                    seen.add(key)\n                    result.append(value)\n            return result\n\n        strong = unique(strong)\n        strong_keys = {cls._compact_identifier(token) for token in strong}\n        family = unique([\n            token\n            for token in family\n            if cls._compact_identifier(token) not in strong_keys\n        ])\n        return brand, family, strong\n\n    @classmethod\n    def _query_variants(cls, query: str) -> list[str]:\n        normalized = " ".join(query.strip().split())\n        brand, family, strong = cls._model_query_parts(normalized)\n        variants: list[str] = []\n        seen: set[str] = set()\n\n        def add(parts: list[str]) -> None:\n            value = " ".join(part for part in parts if part).strip()\n            key = value.casefold()\n            if value and key not in seen:\n                seen.add(key)\n                variants.append(value)\n\n        if strong:\n            add([brand or "", *family, *strong])\n            add([brand or "", *strong])\n        add([normalized])\n        return variants\n\n    async def find_offers(\n        self,\n        query: str,\n        limit: int = 5,\n    ) -> list[ProductOffer]:\n        """Searches 21vek using compact model identity before broad text."""\n\n        normalized_query = " ".join(query.strip().split())\n        if len(normalized_query) < 3 or limit <= 0:\n            return []\n\n        variants = self._query_variants(normalized_query)\n        _, _, strong = self._model_query_parts(normalized_query)\n        strong_keys = [self._compact_identifier(token) for token in strong]\n        unique_offers: dict[str, ProductOffer] = {}\n        errors: list[SourceUnavailableError] = []\n\n        for source_query in variants:\n            try:\n                offers = await self._find_offers_once(\n                    source_query,\n                    limit=max(limit, 20),\n                )\n            except SourceUnavailableError as error:\n                errors.append(error)\n                continue\n\n            if strong_keys:\n                exact = [\n                    offer\n                    for offer in offers\n                    if any(\n                        key in self._compact_identifier(offer.title)\n                        for key in strong_keys\n                    )\n                ]\n                if exact:\n                    return exact[:limit]\n\n            for offer in offers:\n                unique_offers.setdefault(offer.url, offer)\n\n        if unique_offers:\n            return list(unique_offers.values())[:limit]\n        if errors and len(errors) == len(variants):\n            raise errors[0]\n        return []\n\n'''
    text = text[:insert_at] + wrapper + text[insert_at:]
    path.write_text(text)


def main() -> None:
    patch_selection_flow()
    patch_search_handler()
    patch_twenty_one_vek()


if __name__ == "__main__":
    main()
