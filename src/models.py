from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
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


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)  # 화해 ingredient.id 그대로 사용
    name = Column(Text, nullable=False)
    ewg = Column(Text)
    is_twenty = Column(Boolean, default=False)
    is_allergy = Column(Boolean, default=False)
    formulation_purpose = Column(Text)
    purpose_groups = Column(Text)  # JSON 배열 string
    fetched_at = Column(Text, default=lambda: datetime.now().isoformat())


class ProductIngredient(Base):
    __tablename__ = "product_ingredients"

    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), primary_key=True)
    position = Column(Integer, nullable=False)  # 첨가 순서 (1부터)

    __table_args__ = (
        Index("idx_pi_ingredient", "ingredient_id"),
    )


class Effect(Base):
    __tablename__ = "effects"

    id = Column(Integer, primary_key=True)  # 화해 effect.id 그대로 사용
    name = Column(Text, nullable=False)


class ProductEffect(Base):
    __tablename__ = "product_effects"

    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    effect_id = Column(Integer, ForeignKey("effects.id"), primary_key=True)
    score = Column(Integer, nullable=False)
    is_analyzing = Column(Boolean, default=False)
    collected_at = Column(Text, default=lambda: datetime.now().isoformat())

    __table_args__ = (
        Index("idx_pe_effect", "effect_id"),
    )


class EffectEvidence(Base):
    __tablename__ = "effect_evidences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, nullable=False)
    effect_id = Column(Integer, nullable=False)
    evidence_type = Column(Text, nullable=False)
    result_text = Column(Text, nullable=False)

    __table_args__ = (
        Index("idx_evidences_lookup", "product_id", "effect_id"),
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
