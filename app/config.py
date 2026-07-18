import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    price_database_path: str = "data/magazinnik.sqlite3"
    price_alert_interval_seconds: int = 21_600


def load_config() -> Config:
    """Загружает и проверяет настройки приложения."""

    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        raise RuntimeError(
            "Не найден BOT_TOKEN. Проверь файл .env."
        )

    return Config(
        bot_token=bot_token,
        price_database_path=os.getenv(
            "PRICE_DATABASE_PATH",
            "data/magazinnik.sqlite3",
        ),
        price_alert_interval_seconds=max(
            300,
            int(os.getenv("PRICE_ALERT_INTERVAL_SECONDS", "21600")),
        ),
    )
