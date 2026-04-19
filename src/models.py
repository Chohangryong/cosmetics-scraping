from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import (
    Column,
    Integer,
    Float,
    Text,
    create_engine,
    Index,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False)
    product_id = Column(Text, nullable=False)
    product_name = Column(Text, nullable=False)
    brand = Column(Text)
    first_seen_at = Column(Text, default=lambda: datetime.now().isoformat())
    last_seen_at = Column(Text, default=lambda: datetime.now().isoformat())

    __table_args__ = (
        Index("idx_products_platform", "platform", "product_id", unique=True),
    )


class RankingSnapshot(Base):
    __tablename__ = "ranking_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False)
    product_id = Column(Integer, nullable=False)
    platform = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    rank = Column(Integer, nullable=False)
    original_price = Column(Integer)
    sale_price = Column(Integer)
    discount_rate = Column(Integer)
    rating = Column(Float)
    review_count = Column(Integer)
    review_score = Column(Integer)
    badge = Column(Text)
    collected_at = Column(Text, nullable=False)

    __table_args__ = (
        Index("idx_snapshots_lookup", "platform", "category", "collected_at"),
        Index("idx_snapshots_product", "product_id", "collected_at"),
    )


class RankingItem(BaseModel):
    """Spider가 yield하는 dict의 검증 스키마"""
    platform: str
    category: str
    product_id: str
    rank: int
    brand: str = ""
    name: str = ""
    original_price: int | None = None
    sale_price: int | None = None
    discount_rate: int | None = None
    rating: float | None = None
    review_count: int | None = None
    review_score: int | None = None
    badge: str = ""


def get_engine(db_path: str = "data/beauty_ranking.db"):
    engine = create_engine(f"sqlite:///{db_path}", echo=False, poolclass=NullPool)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()
    return engine


def create_tables(engine):
    Base.metadata.create_all(engine)


def migrate_db(engine) -> None:
    """기존 DB에 누락된 컬럼 추가 (idempotent)"""
    with engine.connect() as conn:
        for col in ["review_count INTEGER", "review_score INTEGER"]:
            try:
                conn.execute(text(f"ALTER TABLE ranking_snapshots ADD COLUMN {col}"))
                conn.commit()
            except Exception:
                pass  # 이미 존재하면 무시


def get_session(engine) -> Session:
    return sessionmaker(bind=engine)()
