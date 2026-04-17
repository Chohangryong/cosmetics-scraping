"""카테고리별 랜덤 4개 상품 DB 데이터 vs 실제 사이트 검증 (라이브 테스트)

실행: pytest tests/test_validate_live.py -m live -v
"""
import asyncio
import random
import re
import sqlite3

import pytest
from scrapling.fetchers import StealthyFetcher

DB_PATH = "data/beauty_ranking.db"
BASE_URL = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={}"
CATEGORIES = ["skincare", "makeup", "suncare"]
SAMPLE_N = 4
REVIEW_COUNT_TOLERANCE = 10


def _latest_session() -> str:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT session_id FROM ranking_snapshots ORDER BY session_id DESC LIMIT 1")
    session_id = cur.fetchone()[0]
    conn.close()
    return session_id


def _load_samples(session_id: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    items = []
    for cat in CATEGORIES:
        cur.execute(
            """SELECT p.product_id, p.product_name, p.brand, rs.rank,
                      rs.rating, rs.review_count
               FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
               WHERE rs.session_id=? AND rs.category=?
               ORDER BY RANDOM() LIMIT ?""",
            (session_id, cat, SAMPLE_N),
        )
        for r in cur.fetchall():
            items.append({
                "category": cat, "product_id": r[0], "name": r[1],
                "brand": r[2], "rank": r[3], "rating": r[4], "review_count": r[5],
            })
    conn.close()
    return items


def _parse_int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"[\d,]+", text)
    return int(m.group().replace(",", "")) if m else None


def _parse_float(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"[\d.]+", text)
    return float(m.group()) if m else None


async def _fetch_live(fetcher: StealthyFetcher, product_id: str) -> dict:
    page = await fetcher.async_fetch(
        BASE_URL.format(product_id),
        headless=True,
        network_idle=False,
        disable_resources=False,
        wait_selector="span.rating",
        wait_selector_state="visible",
    )
    rating = _parse_float(page.css("span.rating::text").get())
    if rating and rating > 5:
        rating = None
    review_count = _parse_int(
        page.css('[class*="GoodsDetailTabs_review-count"]::text').get()
    )
    return {"rating": rating, "review_count": review_count}


@pytest.mark.live
class TestLiveValidation:
    def setup_method(self):
        random.seed(42)
        self.session_id = _latest_session()
        self.items = _load_samples(self.session_id)
        self.fetcher = StealthyFetcher(auto_match=False)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_rating_and_review_count(self, category):
        items = [i for i in self.items if i["category"] == category]
        assert items, f"{category} 샘플 없음"
        failures = []
        for item in items:
            actual = self._run(_fetch_live(self.fetcher, item["product_id"]))
            if item["rating"] is not None and actual["rating"] is not None:
                assert abs(item["rating"] - actual["rating"]) < 0.05, (
                    f"{item['brand']} 평점 불일치: DB={item['rating']} SITE={actual['rating']}"
                )
            if item["review_count"] is not None and actual["review_count"] is not None:
                diff = abs(item["review_count"] - actual["review_count"])
                if diff > REVIEW_COUNT_TOLERANCE:
                    failures.append(
                        f"{item['brand']} 리뷰수 불일치: DB={item['review_count']} SITE={actual['review_count']}"
                    )
        assert not failures, "\n".join(failures)
