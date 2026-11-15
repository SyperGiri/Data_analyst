"""Тесты Pydantic-схем: проверяем парсинг дат, enum-статусы и edge-кейсы."""

import pytest
from pydantic import ValidationError

from src.models.schemas import RawRequest, RawResponse


def _request(**overrides):
    data = dict(
        message_id=111733031,
        request_number=21986763,
        pub_date="04.02.2019",
        okrug="ЦАО",
        district="Тверской",
        object_address="1-й Самотёчный переулок д.18",
        category="Дворовые территории",
        topic="Неубранная дворовая территория",
        sla_date="14.02.2019",
        status="Опубликован",
    )
    data.update(overrides)
    return RawRequest(**data)


def test_valid_request_parsed():
    r = _request()
    assert r.pub_date.year == 2019 and r.pub_date.month == 2


def test_empty_sla_date_becomes_none():
    assert _request(sla_date="").sla_date is None


def test_missing_okrug_allowed_for_transport():
    r = _request(okrug=None, district=None,
                 category="Общественный транспорт",
                 topic="Несоблюдение маршрута/графика")
    assert r.okrug is None


def test_invalid_status_raises():
    with pytest.raises(ValidationError):
        _request(status="Удалён")


def test_invalid_date_raises():
    with pytest.raises(ValidationError):
        _request(pub_date="31.02.2019")


def test_response_valid():
    resp = RawResponse(
        request_number=21985694, message_id=111731854,
        okrug="ВАО", district="Вешняки",
        object_address="улица Старый Гай д.1 к.4",
        category="Дворовые территории",
        topic="Некачественное содержание катка",
        response_date="04.02.2019",
    )
    assert resp.response_date.day == 4