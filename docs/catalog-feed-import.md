# Импорт товарного фида

Импорт поддерживает JSON, JSONL и NDJSON. Перед первым реальным запуском рекомендуется выполнить dry-run.

## Настройка хранилища

```env
CATALOG_DATABASE_PATH=data/catalog.sqlite3
```

Также поддерживается существующий JSON backend через `CATALOG_STORAGE_PATH`.

## Обычный batch и полный snapshot

Обычный импорт добавляет или обновляет только записи из файла. Ранее загруженные офферы сохраняют своё состояние.

Snapshot обозначает **полную выгрузку одного источника**. После успешного upsert офферы этого источника, отсутствующие в новом файле, атомарно получают `available=false`. Другие источники не изменяются.

Защитные ограничения snapshot:

- файл должен содержать хотя бы одну валидную запись;
- все записи должны принадлежать одному источнику;
- partial mode запрещён;
- dry-run заранее показывает `deactivated_offers`;
- обновления и отключения сохраняются одной транзакцией и совместно откатываются при ошибке.

## Импорт через Telegram

Доступ ограничивается теми же chat ID, что и другие административные команды:

```env
CATALOG_ADMIN_CHAT_IDS=123456789
CATALOG_FEED_MAX_BYTES=2097152
CATALOG_FEED_CONFIRM_TTL_SECONDS=900
CATALOG_FEED_MAX_PENDING=20
```

1. Отправить боту `.json`, `.jsonl` или `.ndjson` документ.
2. Для обычного batch указать подпись:

```text
/catalog_feed Supplier feed
```

3. Для полной выгрузки одного источника указать:

```text
/catalog_feed_snapshot Supplier feed
```

Если каждая запись уже содержит `source`, название после команды можно не указывать.

Бот выполнит dry-run и покажет будущие `created`, `merged`, `updated` и `deactivated` без изменения каталога. Для реального импорта нужно выполнить выданную одноразовую команду:

```text
/catalog_feed_confirm TOKEN
```

Отмена:

```text
/catalog_feed_cancel TOKEN
```

Статус и ограничения:

```text
/catalog_feed_status
```

Токен привязан к пользователю и чату, удаляется после первого подтверждения и автоматически истекает. Файл хранится только в памяти до подтверждения или окончания TTL. Через Telegram partial mode намеренно недоступен.

## Проверка через CLI

Обычный dry-run:

```bash
python scripts/import_catalog_feed.py \
  docs/catalog-feed.example.json \
  --dry-run
```

Snapshot dry-run:

```bash
python scripts/import_catalog_feed.py supplier.json \
  --source "Supplier feed" \
  --snapshot \
  --dry-run
```

После проверки убрать `--dry-run` для реального импорта.

Для JSONL:

```bash
python scripts/import_catalog_feed.py feed.jsonl --format jsonl
```

Обычный partial batch доступен только через CLI:

```bash
python scripts/import_catalog_feed.py feed.jsonl \
  --format jsonl \
  --allow-partial
```

`--snapshot` и `--allow-partial` несовместимы.

## Поля записи

Обязательные:

- `source` — источник; можно заменить глобальным `--source` или источником в Telegram-подписи;
- `title` или `name` — название товара;
- `url` — абсолютная HTTP/HTTPS ссылка.

Опциональные:

- `external_id` или `sku`; если отсутствуют, стабильный ID строится из URL;
- `price`, `currency`, `available`, `updated_at`;
- `brand`, `model`, `memory`, `color`, `revision`;
- `ean`, `gtin`, `upc`, `mpn`;
- объект `identity` с теми же идентификационными полями.

`updated_at` передаётся в ISO-8601. Цена должна быть неотрицательным числом. Поле `available` принимает boolean или значения `in_stock`/`out_of_stock`.

## Коды завершения CLI

- `0` — импорт или dry-run без ошибок;
- `1` — операция выполнена, но обнаружены невалидные записи, разрешённые partial mode;
- `2` — фид отклонён целиком.
