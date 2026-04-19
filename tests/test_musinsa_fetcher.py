import asyncio
import os
import tempfile

import pytest

from src.models import RankingItem, RankingSnapshot


def test_ranking_item_has_review_score():
    item = RankingItem(
        platform="musinsa",
        category="skincare",
        product_id="12345",
        rank=1,
        brand="에스트라",
        name="아토베리어365 크림",
        sale_price=47520,
        original_price=66000,
        discount_rate=28,
        review_score=98,
        review_count=20028,
    )
    assert item.review_score == 98


def test_ranking_item_review_score_optional():
    item = RankingItem(
        platform="oliveyoung",
        category="skincare",
        product_id="oy001",
        rank=1,
    )
    assert item.review_score is None


from src.storage import save_to_db
from src.models import get_engine, create_tables, migrate_db


def test_save_to_db_includes_review_score():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        items = [{
            "platform": "musinsa",
            "category": "skincare",
            "product_id": "3992824",
            "rank": 1,
            "brand": "에스트라",
            "name": "아토베리어365 크림 80ml",
            "sale_price": 47520,
            "original_price": 66000,
            "discount_rate": 28,
            "review_score": 98,
            "review_count": 20028,
            "badge": "누적 판매 N만 돌파",
        }]
        save_to_db(items, session_id="test_session", db_path=db_path)

        from sqlalchemy import text as sa_text
        engine = get_engine(db_path)
        with engine.connect() as conn:
            row = conn.execute(
                sa_text("SELECT review_score FROM ranking_snapshots WHERE session_id='test_session'")
            ).fetchone()
        assert row is not None
        assert row[0] == 98
    finally:
        os.unlink(db_path)


from src.musinsa_fetcher import parse_item

SAMPLE_ITEM = {
    "type": "PRODUCT_COLUMN",
    "id": "3992824",
    "info": {
        "brandName": "에스트라",
        "productName": "아토베리어365 크림 80ml 2개",
        "discountRatio": 28,
        "finalPrice": 47520,
    },
    "image": {"rank": 1},
    "onClick": {
        "eventLog": {
            "ga4": {
                "payload": {
                    "original_price": 66000,
                    "item_flag": "누적 판매 N만 돌파",
                }
            },
            "amplitude": {
                "payload": {
                    "reviewScore": "98",
                    "reviewCount": "20028",
                }
            },
        }
    },
}

SAMPLE_ITEM_NONE_FLAG = {**SAMPLE_ITEM, "onClick": {
    "eventLog": {
        "ga4": {"payload": {"original_price": 66000, "item_flag": "none"}},
        "amplitude": {"payload": {"reviewScore": "98", "reviewCount": "20028"}},
    }
}}


def test_parse_item_fields():
    result = parse_item(SAMPLE_ITEM, category="skincare")
    assert result["product_id"] == "3992824"
    assert result["rank"] == 1
    assert result["brand"] == "에스트라"
    assert result["name"] == "아토베리어365 크림 80ml 2개"
    assert result["sale_price"] == 47520
    assert result["original_price"] == 66000
    assert result["discount_rate"] == 28
    assert result["review_score"] == 98
    assert result["review_count"] == 20028
    assert result["badge"] == "누적 판매 N만 돌파"
    assert result["platform"] == "musinsa"
    assert result["rating"] is None


def test_parse_item_badge_none_to_empty():
    result = parse_item(SAMPLE_ITEM_NONE_FLAG, category="skincare")
    assert result["badge"] == ""


@pytest.mark.asyncio
async def test_fetch_category_live():
    """실제 API 호출 — 네트워크 필요"""
    import aiohttp
    from src.musinsa_fetcher import fetch_category, MUSINSA_CONCURRENCY
    semaphore = asyncio.Semaphore(MUSINSA_CONCURRENCY)
    async with aiohttp.ClientSession() as session:
        items = await fetch_category(session, "104001", "skincare", semaphore, max_rank=50)

    assert 1 <= len(items) <= 50
    first = items[0]
    assert first["rank"] == 1
    assert first["platform"] == "musinsa"
    assert first["product_id"]
    assert first["brand"]
    assert first["name"]
    assert isinstance(first["sale_price"], int)
    assert first["review_score"] is None or isinstance(first["review_score"], int)
