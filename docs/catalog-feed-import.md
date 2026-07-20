# Импорт товарного фида

Импорт поддерживает JSON, JSONL и NDJSON. Перед первым реальным запуском рекомендуется выполнить dry-run.

## Настройка хранилища

```env
CATALOG_DATABASE_PATH=data/catalog.sqlite3
```

Также поддерживается существующий JSON backend через `CATALOG_STORAGE_PATH`.

## Проверка без изменения каталога

```bash
python scripts/import_catalog_feed.py \
  docs/catalog-feed.example.json \
  --dry-run
```

## Реальный импорт

```bash
python scripts/import_catalog_feed.py feed.json
```

Для JSONL:

```bash
python scripts/import_catalog_feed.py feed.jsonl --format jsonl
```

Если поле `source` отсутствует во всех строках:

```bash
python scripts/import_catalog_feed.py feed.jsonl \
  --format jsonl \
  --source "Supplier feed"
```

По умолчанию наличие хотя бы одной невалидной записи отменяет весь импорт. Явно разрешить загрузку валидных строк можно через:

```bash
python scripts/import_catalog_feed.py feed.jsonl \
  --format jsonl \
  --allow-partial
```

## Поля записи

Обязательные:

- `source` — источник; можно заменить глобальным `--source`;
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
