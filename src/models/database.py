"""ORM-модели нормализованной схемы SQLite (3НФ).

Справочники (dim_*) хранят текстовые атрибуты по одному разу;
факты (fact_*) — только суррогатные FK на справочники + бизнес-метрики.
message_id уникален: это гарантирует идемпотентность загрузки (п.4 ТЗ).
"""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass

# SQLite-движок (файл БД будет создан в корне проекта)
engine = create_engine("sqlite:///mos_gov.db", echo=False)

class Okrug(Base):
    __tablename__ = "dim_okrug"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    districts: Mapped[list["District"]] = relationship(back_populates="okrug")


class District(Base):
    __tablename__ = "dim_raion"
    id: Mapped[int] = mapped_column(primary_key=True)
    okrug_id: Mapped[int] = mapped_column(ForeignKey("dim_okrug.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    okrug: Mapped[Okrug] = relationship(back_populates="districts")
    __table_args__ = (UniqueConstraint("okrug_id", "name"),)


class Category(Base):
    __tablename__ = "dim_category"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    topics: Mapped[list["Topic"]] = relationship(back_populates="category")


class Topic(Base):
    __tablename__ = "dim_topic"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("dim_category.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(256))
    category: Mapped[Category] = relationship(back_populates="topics")
    __table_args__ = (UniqueConstraint("category_id", "name"),)


class Request(Base):
    """Факт: заявка гражданина. message_id — бизнес-ключ источника."""

    __tablename__ = "fact_request"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    request_number: Mapped[int] = mapped_column(Integer, index=True)
    object_address: Mapped[str] = mapped_column(String(256))
    pub_date: Mapped[date] = mapped_column(Date)
    sla_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_raion.id"), nullable=True, index=True
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_topic.id"), nullable=True, index=True
    )


class Response(Base):
    """Факт: ответ ведомства. Привязан к заявке через message_id."""

    __tablename__ = "fact_response"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("fact_request.message_id"), unique=True
    )
    request_number: Mapped[int] = mapped_column(Integer, index=True)
    response_date: Mapped[date] = mapped_column(Date)