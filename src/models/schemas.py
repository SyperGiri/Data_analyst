"""Pydantic-схемы для валидации сырых данных портала «Наш город».

Применяются на этапе извлечения (extraction) и перед загрузкой (loading):
каждая строка XLSX проходит через эти модели. Невалидные строки
отбрасываются или пишутся в отчёт об ошибках — в БД они не попадают.
"""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class ResponseStatus(str, Enum):
    """Допустимые статусы подготовки ответа (бизнес-справочник)."""

    PUBLISHED = "Опубликован"
    PREPARING = "Готовится"
    MODERATION = "На модерации"


def _parse_date(v: str | None) -> date | None:
    """Парсит дату из формата 'DD.MM.YYYY'; пустая строка -> None."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        try:
            return datetime.strptime(v, "%d.%m.%Y").date()
        except ValueError:
            raise ValueError(f"Неверный формат даты: {v}. Ожидался ДД.ММ.ГГГГ")
    return v


class RawRequest(BaseModel):
    """Строка файла «Опубликованные_сообщения.xlsx» (заявка гражданина)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    message_id: int
    request_number: int
    pub_date: date
    okrug: str | None = None          # пусто для общественного транспорта
    district: str | None = None
    object_address: str
    category: str
    topic: str
    sla_date: date | None = None      # регламентный срок может отсутствовать
    status: ResponseStatus

    @field_validator("pub_date", "sla_date", mode="before")
    @classmethod
    def parse_dates(cls, v: str | None) -> date | None:
        return _parse_date(v)

    @field_validator("object_address", "category", "topic")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Поле обязательно и не может быть пустым")
        return v


class RawResponse(BaseModel):
    """Строка файла «Опубликованные_ответы.xlsx» (ответ ведомства)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    request_number: int
    message_id: int
    okrug: str | None = None
    district: str | None = None
    object_address: str
    category: str
    topic: str
    response_date: date

    @field_validator("response_date", mode="before")
    @classmethod
    def parse_response_date(cls, v: str | None) -> date | None:
        return _parse_date(v)