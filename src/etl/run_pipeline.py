"""
ETL-пайплайн: Извлечение, валидация и идемпотентная загрузка данных в SQLite.
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.models.database import (
    Base, Category, District, Okrug, Request, Response, Topic, engine
)
from src.models.schemas import RawRequest, RawResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REQUESTS_FILE = BASE_DIR / "data" / "Опубликованные_сообщения.xlsx"
RESPONSES_FILE = BASE_DIR / "data" / "Опубликованные_ответы.xlsx"

# Маппинг колонок Excel -> имена полей Pydantic
REQUESTS_COL_MAP = {
    "ID сообщения": "message_id",
    "Номер заявки": "request_number",
    "Дата публикации сообщения": "pub_date",
    "Округ": "okrug",
    "Район": "district",
    "Объект": "object_address",
    "Категория объекта": "category",
    "Проблемная тема": "topic",
    "Регламентный срок подготовки ответа": "sla_date",
    "Статус подготовки ответа": "status",
}

RESPONSES_COL_MAP = {
    "Номер заявки": "request_number",
    "ID сообщения": "message_id",
    "Округ": "okrug",
    "Район": "district",
    "Объект": "object_address",
    "Категория объекта": "category",
    "Проблемная тема": "topic",
    "Дата публикации ответа": "response_date",
}


def _parse_date(v) -> "datetime | None":
    """Универсальный парсер даты: принимает str, datetime, date или None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if hasattr(v, "date"):  # pandas Timestamp
        return v.date()
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        try:
            return datetime.strptime(v, "%d.%m.%Y").date()
        except ValueError:
            raise ValueError(f"Неверный формат даты: '{v}'. Ожидался ДД.ММ.ГГГГ")
    raise ValueError(f"Неподдерживаемый тип даты: {type(v).__name__}")


def validate_dataframe(
    df: pd.DataFrame, model_cls, col_map: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Валидирует DataFrame через Pydantic."""
    df = df.rename(columns=col_map)

    missing = set(model_cls.model_fields.keys()) - set(df.columns)
    if missing:
        raise ValueError(f"В DataFrame отсутствуют колонки: {missing}")

    valid_records = []
    errors = []
    df = df.where(pd.notnull(df), None)

    for idx, row in df.iterrows():
        try:
            data = row.to_dict()
            # Применяем парсер дат вручную ДО валидации Pydantic
            for date_field in ("pub_date", "sla_date", "response_date"):
                if date_field in data:
                    data[date_field] = _parse_date(data[date_field])

            validated = model_cls.model_validate(data).model_dump()
            # ВАЖНО: Мы НЕ делаем .isoformat() здесь! 
            # SQLAlchemy сама корректно обработает объекты datetime.date для типа Date.
            valid_records.append(validated)
        except Exception as e:
            errors.append({"row": int(idx), "error": str(e)})

    return valid_records, errors


def get_or_create(session, model, unique_field: str, value: str | None):
    if value is None:
        return None
    stmt = select(model).where(getattr(model, unique_field) == value)
    result = session.execute(stmt).scalar_one_or_none()
    if result:
        return result.id
    new_record = model(**{unique_field: value})
    session.add(new_record)
    session.flush()
    return new_record.id


def get_or_create_district(session, okrug_id: int, name: str):
    stmt = select(District).where(
        District.okrug_id == okrug_id, District.name == name
    )
    result = session.execute(stmt).scalar_one_or_none()
    if result:
        return result.id
    new_district = District(okrug_id=okrug_id, name=name)
    session.add(new_district)
    session.flush()
    return new_district.id


def get_or_create_topic(session, category_id: int, name: str):
    stmt = select(Topic).where(
        Topic.category_id == category_id, Topic.name == name
    )
    result = session.execute(stmt).scalar_one_or_none()
    if result:
        return result.id
    new_topic = Topic(category_id=category_id, name=name)
    session.add(new_topic)
    session.flush()
    return new_topic.id


def run_etl():
    logger.info("🚀 Запуск ETL-пайплайна...")
    Base.metadata.create_all(engine)
    logger.info("✅ Таблицы БД проверены/созданы.")

    with Session(engine) as session:

        # ===== ЗАЯВКИ =====
        logger.info(f"📖 Чтение {REQUESTS_FILE.name}...")
        df_req = pd.read_excel(REQUESTS_FILE)
        logger.info(f"   Колонки в Excel: {list(df_req.columns)}")

        valid_reqs, errors_req = validate_dataframe(df_req, RawRequest, REQUESTS_COL_MAP)

        if errors_req:
            logger.warning(f"⚠️ Пропущено {len(errors_req)} невалидных строк.")
            for err in errors_req[:3]:
                logger.warning(f"   Пример ошибки: {err}")

        logger.info(f"✅ Валидно записей заявок: {len(valid_reqs)}")

        for req in valid_reqs:
            okrug_id = get_or_create(session, Okrug, "name", req.get("okrug"))

            district_id = None
            if req.get("district") and okrug_id:
                district_id = get_or_create_district(session, okrug_id, req["district"])

            category_id = get_or_create(session, Category, "name", req.get("category"))

            topic_id = None
            if req.get("topic") and category_id:
                topic_id = get_or_create_topic(session, category_id, req["topic"])

            status_val = req["status"]
            if hasattr(status_val, "value"):
                status_val = status_val.value

            stmt = (
                sqlite_insert(Request)
                .values(
                    message_id=req["message_id"],
                    request_number=req["request_number"],
                    object_address=req["object_address"],
                    pub_date=req["pub_date"],
                    sla_date=req.get("sla_date"),
                    status=status_val,
                    district_id=district_id,
                    topic_id=topic_id,
                )
                .on_conflict_do_update(
                    index_elements=["message_id"],
                    set_={
                        "request_number": req["request_number"],
                        "object_address": req["object_address"],
                        "pub_date": req["pub_date"],
                        "sla_date": req.get("sla_date"),
                        "status": status_val,
                        "district_id": district_id,
                        "topic_id": topic_id,
                    },
                )
            )
            session.execute(stmt)

        # ===== ОТВЕТЫ =====
        logger.info(f"📖 Чтение {RESPONSES_FILE.name}...")
        df_resp = pd.read_excel(RESPONSES_FILE)
        logger.info(f"   Колонки в Excel: {list(df_resp.columns)}")

        valid_resps, errors_resp = validate_dataframe(
            df_resp, RawResponse, RESPONSES_COL_MAP
        )

        if errors_resp:
            logger.warning(f"⚠️ Пропущено {len(errors_resp)} невалидных строк.")
            for err in errors_resp[:3]:
                logger.warning(f"   Пример ошибки: {err}")

        logger.info(f"✅ Валидно записей ответов: {len(valid_resps)}")

        for resp in valid_resps:
            stmt = (
                sqlite_insert(Response)
                .values(
                    message_id=resp["message_id"],
                    request_number=resp["request_number"],
                    response_date=resp["response_date"],
                )
                .on_conflict_do_update(
                    index_elements=["message_id"],
                    set_={
                        "request_number": resp["request_number"],
                        "response_date": resp["response_date"],
                    },
                )
            )
            session.execute(stmt)

        session.commit()

    logger.info("🎉 ETL-пайплайн успешно завершён! Данные загружены в SQLite.")


if __name__ == "__main__":
    run_etl()