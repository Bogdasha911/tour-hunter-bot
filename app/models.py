from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SearchProfileModel(Base):
    __tablename__ = "search_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    departure_city: Mapped[str] = mapped_column(String(100), default="Москва")
    destination: Mapped[str] = mapped_column(String(100), default="Дубай")
    adults: Mapped[int] = mapped_column(Integer, default=1)
    children: Mapped[int] = mapped_column(Integer, default=0)
    budget: Mapped[int] = mapped_column(Integer, default=60000)
    nights_min: Mapped[int] = mapped_column(Integer, default=3)
    nights_max: Mapped[int] = mapped_column(Integer, default=10)
    date_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    min_drop_percent: Mapped[float] = mapped_column(Float, default=7.0)
    max_results_per_source: Mapped[int] = mapped_column(Integer, default=80)


class DealModel(Base):
    __tablename__ = "deals"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "hotel_name",
            "departure_date",
            "nights",
            "meal",
            "room_type",
            "price",
            name="uq_deal_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    hotel_name: Mapped[str] = mapped_column(String(300), index=True)
    price: Mapped[int] = mapped_column(Integer, index=True)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    departure_date: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    nights: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meal: Mapped[str | None] = mapped_column(String(120), nullable=True)
    room_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DealAggregateModel(Base):
    __tablename__ = "deal_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "source", "hotel_name", "departure_date", "nights", "meal", "room_type", name="uq_deal_aggregate_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    hotel_name: Mapped[str] = mapped_column(String(300), index=True)
    departure_date: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    nights: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meal: Mapped[str | None] = mapped_column(String(120), nullable=True)
    room_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    min_price: Mapped[int] = mapped_column(Integer, index=True)
    last_price: Mapped[int] = mapped_column(Integer, index=True)
    max_price: Mapped[int] = mapped_column(Integer, index=True)
    observations: Mapped[int] = mapped_column(Integer, default=1)
    last_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AlertLogModel(Base):
    __tablename__ = "alert_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(500), unique=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SourceStateModel(Base):
    __tablename__ = "source_states"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
