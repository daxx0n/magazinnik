import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str


def load_config() -> Config:
    """Загружает и проверяет настройки приложения."""

    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        raise RuntimeError(
            "Не найден BOT_TOKEN. Проверь файл .env."
        )

    return Config(bot_token=bot_token)