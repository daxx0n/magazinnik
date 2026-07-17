class SourceError(Exception):
    """Базовая ошибка источника цен."""


class InvalidProductUrlError(SourceError):
    """Передана некорректная ссылка на товар."""


class ProductNotFoundError(SourceError):
    """Не удалось получить данные товара."""


class SourceUnavailableError(SourceError):
    """Источник временно недоступен."""