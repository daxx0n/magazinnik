from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.models.catalog_feed import CatalogFeedImportReport
from app.services.catalog_feed_upload import (
    CatalogFeedSessionError,
    CatalogFeedUploadManager,
)


router = Router(name="catalog-feed")
logger = logging.getLogger(__name__)
catalog_feed_upload_manager: CatalogFeedUploadManager | None = None


@dataclass(frozen=True, slots=True)
class CatalogFeedRequest:
    """Режим и общий источник из подписи Telegram-документа."""

    snapshot: bool
    default_source: str


def initialize_catalog_feed_upload(
    manager: CatalogFeedUploadManager,
) -> None:
    """Подключает общий менеджер загрузки товарных фидов."""

    global catalog_feed_upload_manager
    catalog_feed_upload_manager = manager


@router.message(F.document)
async def handle_catalog_feed_document(
    message: Message,
    bot: Bot,
) -> None:
    """Выполняет dry-run прикреплённого JSON/JSONL-фида."""

    request = parse_catalog_feed_request(message.caption)
    if request is None:
        return
    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    manager = get_catalog_feed_upload_manager()
    if manager is None:
        await message.answer("Импорт товарных фидов не инициализирован.")
        return

    document = message.document
    user = message.from_user
    if document is None or user is None:
        await message.answer("Не удалось определить файл или пользователя.")
        return

    filename = document.file_name or "feed.json"
    try:
        manager.format_from_filename(filename)
    except ValueError as error:
        await message.answer(str(error))
        return

    file_size = document.file_size or 0
    if file_size > manager.config.max_file_bytes:
        await message.answer(
            "Файл слишком большой. Максимальный размер: "
            f"{format_bytes(manager.config.max_file_bytes)}."
        )
        return

    status_message = await message.answer(
        "🔍 Загружаю фид и выполняю dry-run..."
    )
    try:
        destination = BytesIO()
        await bot.download(document, destination=destination)
        if destination.tell() > manager.config.max_file_bytes:
            await status_message.edit_text(
                "Файл превышает допустимый размер: "
                f"{format_bytes(manager.config.max_file_bytes)}."
            )
            return
        destination.seek(0)
        text = destination.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        await status_message.edit_text(
            "Файл должен быть текстовым JSON/JSONL в кодировке UTF-8."
        )
        return
    except Exception:
        logger.exception("Catalog feed document download failed")
        await status_message.edit_text("Не удалось загрузить файл из Telegram.")
        return

    try:
        session, report = manager.prepare(
            chat_id=message.chat.id,
            user_id=user.id,
            filename=filename,
            text=text,
            default_source=request.default_source or None,
            snapshot=request.snapshot,
        )
    except Exception:
        logger.exception("Catalog feed dry-run failed")
        await status_message.edit_text("Не удалось проверить товарный фид.")
        return

    if session is None:
        await status_message.edit_text(
            format_catalog_feed_report(
                report,
                title="❌ Фид не готов к импорту",
            )
        )
        return

    ttl_minutes = int(manager.config.confirmation_ttl_seconds // 60)
    dry_run_title = (
        "✅ Snapshot dry-run завершён"
        if request.snapshot
        else "✅ Dry-run завершён"
    )
    await status_message.edit_text(
        format_catalog_feed_report(
            report,
            title=dry_run_title,
        )
        + "\n\n"
        + "Для одноразового импорта выполни:\n"
        + f"/catalog_feed_confirm {session.token}\n\n"
        + "Отмена:\n"
        + f"/catalog_feed_cancel {session.token}\n\n"
        + f"Подтверждение действует {ttl_minutes} мин."
    )


@router.message(Command("catalog_feed", "catalog_feed_snapshot"))
async def handle_catalog_feed_help(message: Message) -> None:
    """Объясняет безопасный процесс загрузки фида."""

    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    await message.answer(
        "Прикрепи файл .json, .jsonl или .ndjson и добавь подпись:\n\n"
        "/catalog_feed\n\n"
        "Если в строках нет поля source, укажи общий источник:\n\n"
        "/catalog_feed Supplier feed\n\n"
        "Для полной выгрузки одного источника используй:\n\n"
        "/catalog_feed_snapshot Supplier feed\n\n"
        "Snapshot после dry-run пометит недоступными офферы источника, "
        "которые отсутствуют в новом файле. Каталог изменится только "
        "после одноразовой команды подтверждения."
    )


@router.message(Command("catalog_feed_confirm"))
async def handle_catalog_feed_confirm(message: Message) -> None:
    """Подтверждает одноразовый импорт проверенного фида."""

    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    manager = get_catalog_feed_upload_manager()
    token = command_argument(message.text)
    user = message.from_user
    if manager is None:
        await message.answer("Импорт товарных фидов не инициализирован.")
        return
    if token is None or user is None:
        await message.answer("Использование: /catalog_feed_confirm TOKEN")
        return

    status_message = await message.answer("📥 Импортирую проверенный фид...")
    try:
        report = manager.confirm(
            token,
            chat_id=message.chat.id,
            user_id=user.id,
        )
    except CatalogFeedSessionError as error:
        await status_message.edit_text(str(error))
        return
    except Exception:
        logger.exception("Confirmed catalog feed import failed")
        await status_message.edit_text(
            "Импорт завершился ошибкой. Каталог не должен быть изменён частично."
        )
        return

    await status_message.edit_text(
        format_catalog_feed_report(
            report,
            title="✅ Товарный фид импортирован",
        )
    )


@router.message(Command("catalog_feed_cancel"))
async def handle_catalog_feed_cancel(message: Message) -> None:
    """Отменяет ожидающий импорт фида."""

    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    manager = get_catalog_feed_upload_manager()
    token = command_argument(message.text)
    user = message.from_user
    if manager is None:
        await message.answer("Импорт товарных фидов не инициализирован.")
        return
    if token is None or user is None:
        await message.answer("Использование: /catalog_feed_cancel TOKEN")
        return

    try:
        session = manager.cancel(
            token,
            chat_id=message.chat.id,
            user_id=user.id,
        )
    except CatalogFeedSessionError as error:
        await message.answer(str(error))
        return

    await message.answer(f"Импорт файла {session.filename} отменён.")


@router.message(Command("catalog_feed_status"))
async def handle_catalog_feed_status(message: Message) -> None:
    """Показывает ограничения и число ожидающих подтверждений."""

    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    manager = get_catalog_feed_upload_manager()
    if manager is None:
        await message.answer("Импорт товарных фидов не инициализирован.")
        return

    config = manager.config
    await message.answer(
        "📥 Импорт товарных фидов\n\n"
        f"Ожидают подтверждения: {manager.pending_count}\n"
        f"Максимальный файл: {format_bytes(config.max_file_bytes)}\n"
        f"TTL подтверждения: {config.confirmation_ttl_seconds:.0f} сек.\n"
        f"Лимит сессий: {config.max_pending_sessions}"
    )


def get_catalog_feed_upload_manager() -> CatalogFeedUploadManager | None:
    return catalog_feed_upload_manager


def parse_catalog_feed_request(
    caption: str | None,
) -> CatalogFeedRequest | None:
    """Разбирает обычный или snapshot импорт из подписи документа."""

    parts = (caption or "").strip().split(maxsplit=1)
    if not parts:
        return None
    command = parts[0].split("@", maxsplit=1)[0].casefold()
    if command == "/catalog_feed":
        snapshot = False
    elif command == "/catalog_feed_snapshot":
        snapshot = True
    else:
        return None
    return CatalogFeedRequest(
        snapshot=snapshot,
        default_source=parts[1].strip() if len(parts) == 2 else "",
    )


def parse_catalog_feed_caption(caption: str | None) -> str | None:
    """Сохраняет совместимый доступ к общему источнику подписи."""

    request = parse_catalog_feed_request(caption)
    return request.default_source if request is not None else None


def command_argument(text: str | None) -> str | None:
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return None
    return parts[1].strip().casefold()


def format_catalog_feed_report(
    report: CatalogFeedImportReport,
    *,
    title: str,
) -> str:
    lines = [
        title,
        "",
        f"Всего записей: {report.total_records}",
        f"Валидных: {report.valid_records}",
        f"Невалидных: {report.invalid_records}",
        f"Новых карточек: {report.created_products}",
        f"Новых привязок: {report.merged_offers}",
        f"Обновлённых офферов: {report.updated_offers}",
        f"Станут недоступными: {report.deactivated_offers}",
    ]
    if report.issues:
        lines.extend(["", "Первые ошибки:"])
        lines.extend(
            f"• запись {issue.record}, {issue.field}: {issue.message}"
            for issue in report.issues[:5]
        )
        if len(report.issues) > 5:
            lines.append(f"• ещё ошибок: {len(report.issues) - 5}")
    return "\n".join(lines)


def format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} МБ"
    if value >= 1024:
        return f"{value / 1024:.1f} КБ"
    return f"{value} Б"


def _is_allowed(message: Message) -> bool:
    raw_ids = os.getenv("CATALOG_ADMIN_CHAT_IDS", "").strip()
    if not raw_ids:
        return True

    allowed_ids: set[int] = set()
    for raw_id in raw_ids.split(","):
        try:
            allowed_ids.add(int(raw_id.strip()))
        except ValueError:
            logger.warning("Invalid CATALOG_ADMIN_CHAT_IDS value: %r", raw_id)

    return message.chat.id in allowed_ids
