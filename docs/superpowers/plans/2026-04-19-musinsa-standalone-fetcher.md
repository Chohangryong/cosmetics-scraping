# 무신사 Standalone Fetcher 분리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 무신사 랭킹 수집을 브라우저 기반 Spider에서 aiohttp 기반 standalone fetcher로 전환하여 카테고리당 50개를 안정적으로 수집한다.

**Architecture:** `BeautyRankingSpider`는 올리브영 전용으로 유지하고, 신규 `musinsa_fetcher.py`가 sections API를 aiohttp로 직접 호출한다. `main.py`에서 두 결과를 합산하여 기존 저장 로직에 전달한다.

**Tech Stack:** Python 3.11, aiohttp, SQLAlchemy, pytest-asyncio

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `src/musinsa_fetcher.py` | 신규 — sections API 호출 + 파싱 |
| `src/config.py` | `MUSINSA_URLS` → `MUSINSA_CATEGORY_CODES` 교체 |
| `src/models.py` | `RankingSnapshot.review_score`, `RankingItem.review_score` 추가, `migrate_db()` 반영 |
| `src/storage.py` | `ranking_snapshots` INSERT에 `review_score` 포함 |
| `src/spider.py` | musinsa session + start_requests 무신사 항목 제거 |
| `src/main.py` | `musinsa_fetcher.fetch_all()` 호출 + 결과 합산 |
| `pyproject.toml` | `aiohttp` 의존성 추가 |
| `tests/test_musinsa_fetcher.py` | 신규 — fetcher 단위 테스트 |

---

### Task 1: aiohttp 의존성 추가

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: pyproject.toml에 aiohttp 추가**

`pyproject.toml`의 `dependencies` 리스트에 `"aiohttp>=3.9"` 추가:

```toml
dependencies = [
    "scrapling>=0.4",
    "sqlalchemy>=2.0",
    "pydantic>=2.0",
    "uvloop; sys_platform != 'win32'",
    "aiohttp>=3.9",
]
```

- [ ] **Step 2: 설치 및 확인**

```bash
cd ~/cosmetics_scraping
.venv/bin/pip install aiohttp>=3.9
.venv/bin/python -c "import aiohttp; print(aiohttp.__version__)"
```

Expected: 버전 문자열 출력 (예: `3.9.5`)

- [ ] **Step 3: 커밋**

```bash
git add pyproject.toml
git commit -m "chore: aiohttp 의존성 추가"
```

---

### Task 2: config.py — MUSINSA_CATEGORY_CODES로 교체

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: MUSINSA_URLS 제거 후 MUSINSA_CATEGORY_CODES 추가**

`src/config.py`에서 `MUSINSA_BASE`와 `MUSINSA_URLS` 블록을 아래로 교체:

```python
# ── 무신사 카테고리 코드 ──
MUSINSA_CATEGORY_CODES: list[tuple[str, str]] = [
    ("104001", "skincare"),
    ("104013", "mask_pack"),
    ("104014", "base_makeup"),
    ("104015", "lip_makeup"),
    ("104016", "eye_makeup"),
    ("104017", "nail"),
    ("104005", "fragrance"),
    ("104002", "suncare"),
    ("104003", "cleansing"),
    ("104006", "hair_care"),
    ("104007", "body_care"),
    ("104009", "shaving"),
    ("104010", "beauty_device"),
    ("104011", "beauty_tool"),
    ("104012", "health_food"),
]
```

- [ ] **Step 2: 문법 오류 없는지 확인**

```bash
cd ~/cosmetics_scraping
.venv/bin/python -c "from src.config import MUSINSA_CATEGORY_CODES; print(len(MUSINSA_CATEGORY_CODES))"
```

Expected: `15`

- [ ] **Step 3: 커밋**

```bash
git add src/config.py
git commit -m "feat[config]: MUSINSA_URLS → MUSINSA_CATEGORY_CODES 교체"
```

---

### Task 3: models.py — review_score 컬럼 추가

**Files:**
- Modify: `src/models.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_musinsa_fetcher.py` 신규 생성:

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd ~/cosmetics_scraping
.venv/bin/pytest tests/test_musinsa_fetcher.py::test_ranking_item_has_review_score -v
```

Expected: FAIL — `RankingItem` has no field `review_score`

- [ ] **Step 3: RankingItem에 review_score 필드 추가**

`src/models.py`의 `RankingItem` 클래스에 필드 추가:

```python
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
    review_score: int | None = None  # 추가: 무신사 0-100 만족도
    badge: str = ""
```

- [ ] **Step 4: RankingSnapshot에 review_score 컬럼 추가**

`src/models.py`의 `RankingSnapshot` 클래스에 컬럼 추가 (`review_count` 바로 아래):

```python
    review_count = Column(Integer)
    review_score = Column(Integer)   # 추가: 무신사 0-100 만족도
    badge = Column(Text)
```

- [ ] **Step 5: migrate_db()에 review_score 추가**

`src/models.py`의 `migrate_db()` 함수 수정:

```python
def migrate_db(engine) -> None:
    """기존 DB에 누락된 컬럼 추가 (idempotent)"""
    with engine.connect() as conn:
        for col in ["review_count INTEGER", "review_score INTEGER"]:
            try:
                conn.execute(text(f"ALTER TABLE ranking_snapshots ADD COLUMN {col}"))
                conn.commit()
            except Exception:
                pass  # 이미 존재하면 무시
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

```bash
.venv/bin/pytest tests/test_musinsa_fetcher.py -v
```

Expected: 2 passed

- [ ] **Step 7: 커밋**

```bash
git add src/models.py tests/test_musinsa_fetcher.py
git commit -m "feat[models]: review_score 컬럼 및 RankingItem 필드 추가"
```

---

### Task 4: storage.py — review_score INSERT 반영

**Files:**
- Modify: `src/storage.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_musinsa_fetcher.py`에 추가:

```python
import tempfile
import os
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/bin/pytest tests/test_musinsa_fetcher.py::test_save_to_db_includes_review_score -v
```

Expected: FAIL — `review_score` not in INSERT statement

- [ ] **Step 3: storage.py INSERT 쿼리에 review_score 추가**

`src/storage.py`의 `save_to_db` 함수에서 `ranking_snapshots` INSERT 쿼리 수정:

```python
                db.execute(
                    text(
                        "INSERT INTO ranking_snapshots "
                        "(session_id, product_id, platform, category, rank, "
                        "original_price, sale_price, discount_rate, rating, review_count, review_score, badge, collected_at) "
                        "VALUES (:session_id, :product_id, :platform, :category, :rank, "
                        ":original_price, :sale_price, :discount_rate, :rating, :review_count, :review_score, :badge, :collected_at)"
                    ),
                    {
                        "session_id": session_id,
                        "product_id": pk,
                        "platform": item.platform,
                        "category": item.category,
                        "rank": item.rank,
                        "original_price": item.original_price,
                        "sale_price": item.sale_price,
                        "discount_rate": item.discount_rate,
                        "rating": item.rating,
                        "review_count": item.review_count,
                        "review_score": item.review_score,
                        "badge": item.badge,
                        "collected_at": now,
                    },
                )
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/bin/pytest tests/test_musinsa_fetcher.py -v
```

Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add src/storage.py tests/test_musinsa_fetcher.py
git commit -m "feat[storage]: ranking_snapshots INSERT에 review_score 포함"
```

---

### Task 5: musinsa_fetcher.py 구현

**Files:**
- Create: `src/musinsa_fetcher.py`
- Modify: `tests/test_musinsa_fetcher.py`

- [ ] **Step 1: 파싱 로직 단위 테스트 작성**

`tests/test_musinsa_fetcher.py`에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/bin/pytest tests/test_musinsa_fetcher.py::test_parse_item_fields -v
```

Expected: FAIL — `musinsa_fetcher` module not found

- [ ] **Step 3: musinsa_fetcher.py 구현**

`src/musinsa_fetcher.py` 신규 생성:

```python
import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

API_URL = "https://api.musinsa.com/api2/hm/web/v5/pans/ranking/sections/231"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.musinsa.com/main/beauty/ranking",
}
MUSINSA_CONCURRENCY = 3
MUSINSA_API_DELAY = 2.0


def parse_item(item: dict, category: str) -> dict:
    info = item.get("info", {})
    ga4 = item.get("onClick", {}).get("eventLog", {}).get("ga4", {}).get("payload", {})
    amp = item.get("onClick", {}).get("eventLog", {}).get("amplitude", {}).get("payload", {})

    flag = ga4.get("item_flag", "")
    badge = "" if flag == "none" else flag

    review_score_raw = amp.get("reviewScore")
    review_count_raw = amp.get("reviewCount")

    return {
        "platform": "musinsa",
        "category": category,
        "product_id": str(item.get("id", "")),
        "rank": item.get("image", {}).get("rank", 0),
        "brand": info.get("brandName", ""),
        "name": info.get("productName", ""),
        "sale_price": info.get("finalPrice"),
        "original_price": ga4.get("original_price"),
        "discount_rate": info.get("discountRatio"),
        "badge": badge,
        "review_score": int(review_score_raw) if review_score_raw is not None else None,
        "review_count": int(review_count_raw) if review_count_raw is not None else None,
        "rating": None,
    }


async def fetch_category(
    session: aiohttp.ClientSession,
    code: str,
    category: str,
    semaphore: asyncio.Semaphore,
    max_rank: int = 50,
) -> list[dict]:
    params = {"storeCode": "beauty", "gf": "A", "categoryCode": code, "page": 1}
    async with semaphore:
        async with session.get(API_URL, params=params, headers=HEADERS) as resp:
            resp.raise_for_status()
            data = await resp.json()
        await asyncio.sleep(MUSINSA_API_DELAY)

    items = []
    for module in data.get("data", {}).get("modules", []):
        for raw_item in module.get("items", []):
            if raw_item.get("type") != "PRODUCT_COLUMN":
                continue
            parsed = parse_item(raw_item, category)
            if parsed["rank"] > max_rank:
                return items
            items.append(parsed)
    return items


async def fetch_all(
    category_codes: list[tuple[str, str]],
    max_rank: int = 50,
) -> list[dict]:
    semaphore = asyncio.Semaphore(MUSINSA_CONCURRENCY)
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_category(session, code, cat, semaphore, max_rank)
            for code, cat in category_codes
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for (code, cat), result in zip(category_codes, results):
        if isinstance(result, Exception):
            log.error(f"무신사 {cat}({code}) 수집 실패: {result}")
        else:
            all_items.extend(result)
    return all_items
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/bin/pytest tests/test_musinsa_fetcher.py -v
```

Expected: 5 passed

- [ ] **Step 5: 커밋**

```bash
git add src/musinsa_fetcher.py tests/test_musinsa_fetcher.py
git commit -m "feat[musinsa]: standalone fetcher 구현 (sections API, aiohttp)"
```

---

### Task 6: spider.py — 무신사 제거

**Files:**
- Modify: `src/spider.py`

- [ ] **Step 1: configure_sessions에서 musinsa session 제거**

`src/spider.py`의 `configure_sessions` 메서드에서 `manager.add("musinsa", ...)` 블록 전체 삭제:

```python
    def configure_sessions(self, manager):
        manager.add(
            "oliveyoung",
            AsyncStealthySession(
                headless=self._headless,
                network_idle=True,
                disable_resources=True,
                blocked_domains=BLOCKED_DOMAINS,
                hide_canvas=True,
                block_webrtc=True,
                timeout=60000,
                google_search=True,
                solve_cloudflare=False,
            ),
            lazy=False,
        )
```

- [ ] **Step 2: start_requests에서 무신사 루프 제거**

`src/spider.py`의 `start_requests` 메서드에서 `MUSINSA_URLS` 관련 루프 전체 삭제:

```python
    async def start_requests(self):
        for url, category in OLIVEYOUNG_URLS:
            yield Request(
                url=url,
                callback=self.parse_oliveyoung,
                sid="oliveyoung",
                meta={"platform": "oliveyoung", "category": category},
            )
```

- [ ] **Step 3: import에서 MUSINSA_URLS 제거**

`src/spider.py` 상단 import 수정:

```python
from src.config import (
    OLIVEYOUNG_URLS,
    ADAPTIVE_MODE,
    BLOCKED_DOMAINS,
    parse_args,
)
```

- [ ] **Step 4: parse_musinsa 메서드 제거**

`src/spider.py`에서 `parse_musinsa` 메서드 전체 삭제 (119~151행).

- [ ] **Step 5: 기존 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_spider.py tests/test_parsers.py -v
```

Expected: 모두 PASS (무신사 관련 테스트가 있다면 해당 항목 삭제 또는 skip 처리)

- [ ] **Step 6: 커밋**

```bash
git add src/spider.py
git commit -m "feat[spider]: 무신사 session 및 파서 제거 (standalone fetcher로 이전)"
```

---

### Task 7: main.py — musinsa_fetcher 통합

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: import 추가**

`src/main.py` 상단에 추가:

```python
import json

from src import musinsa_fetcher
from src.config import MUSINSA_CATEGORY_CODES
```

- [ ] **Step 2: Spider 결과와 무신사 결과 합산으로 교체**

`main.py`의 `main()` 함수에서 spider 실행 이후 로직을 수정:

```python
def main():
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log.info(f"수집 시작 (session: {timestamp}, headless: {args.headless})")

    # 1. 올리브영 (Spider)
    spider = BeautyRankingSpider(
        headless=args.headless,
        crawldir="data/crawl_state",
    )
    spider_result = spider.start(use_uvloop=True)
    oy_items = list(spider_result.items)

    # 2. 무신사 (standalone fetcher)
    log.info("무신사 수집 시작")
    ms_items = asyncio.run(musinsa_fetcher.fetch_all(MUSINSA_CATEGORY_CODES))
    log.info(f"무신사 수집 완료: {len(ms_items)}건")

    all_items = oy_items + ms_items

    # 3. JSONL 백업
    jsonl_path = f"data/ranking_{timestamp}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in all_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    log.info(f"JSONL 저장: {jsonl_path}")

    # 4. DB 저장
    saved = save_to_db(all_items, session_id=timestamp)

    # 5. Rating 보강 (올리브영만)
    oy_ids = [i["product_id"] for i in oy_items]
    if oy_ids:
        log.info(f"Rating 보강 시작: 올리브영 {len(oy_ids)}개 상품")
        enriched = asyncio.run(
            enrich_ratings(oy_ids, session_id=timestamp, headless=args.headless)
        )
        log.info(f"Rating 보강: {enriched}건")

    # 6. 부분 실패 감지
    oy_count = len(oy_items)
    ms_count = len(ms_items)

    if len(all_items) == 0:
        log.error("전체 수집 실패: 0건. 사이트 변경 또는 차단 가능성")
    elif oy_count == 0 or ms_count == 0:
        log.warning(f"부분 실패: 올리브영={oy_count}건, 무신사={ms_count}건")

    # 7. 통계
    log.info(f"총 수집: {len(all_items)}건 (올리브영: {oy_count}, 무신사: {ms_count})")
    log.info(f"DB 저장: {saved}건")
    log.info(f"통계: {spider_result.stats}")
```

> **주의:** 기존 `result.items.to_jsonl(jsonl_path)` 는 Spider 전용 메서드이므로 `all_items` 합산 후에는 표준 json 파일 쓰기로 교체한다.

- [ ] **Step 3: 문법 확인**

```bash
cd ~/cosmetics_scraping
.venv/bin/python -c "from src.main import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
git add src/main.py
git commit -m "feat[main]: musinsa_fetcher 통합, 올리브영+무신사 결과 합산"
```

---

### Task 8: 실제 API 연동 테스트 (live)

**Files:**
- Modify: `tests/test_musinsa_fetcher.py`

- [ ] **Step 1: live 테스트 추가**

`tests/test_musinsa_fetcher.py`에 추가 (pytest mark로 분리):

```python
import asyncio
import pytest


@pytest.mark.asyncio
async def test_fetch_category_live():
    """실제 API 호출 — 네트워크 필요"""
    import aiohttp
    from src.musinsa_fetcher import fetch_category, MUSINSA_CONCURRENCY
    semaphore = asyncio.Semaphore(MUSINSA_CONCURRENCY)
    async with aiohttp.ClientSession() as session:
        items = await fetch_category(session, "104001", "skincare", semaphore, max_rank=50)

    assert len(items) == 50
    first = items[0]
    assert first["rank"] == 1
    assert first["platform"] == "musinsa"
    assert first["product_id"]
    assert first["brand"]
    assert first["name"]
    assert isinstance(first["sale_price"], int)
    assert first["review_score"] is None or isinstance(first["review_score"], int)
```

- [ ] **Step 2: live 테스트 실행**

```bash
cd ~/cosmetics_scraping
.venv/bin/pytest tests/test_musinsa_fetcher.py::test_fetch_category_live -v -s
```

Expected: PASS, 50개 반환 확인

- [ ] **Step 3: 전체 테스트 실행**

```bash
.venv/bin/pytest tests/ -v --ignore=tests/test_validate_live.py
```

Expected: 모두 PASS

- [ ] **Step 4: 커밋**

```bash
git add tests/test_musinsa_fetcher.py
git commit -m "test[musinsa]: live API 연동 테스트 추가"
```

---

### Task 9: 통합 검증

- [ ] **Step 1: 드라이런 — 무신사 단독 수집 확인**

```bash
cd ~/cosmetics_scraping
.venv/bin/python -c "
import asyncio
from src.musinsa_fetcher import fetch_all
from src.config import MUSINSA_CATEGORY_CODES

items = asyncio.run(fetch_all(MUSINSA_CATEGORY_CODES))
print(f'총 수집: {len(items)}건')
cats = {}
for i in items:
    cats[i['category']] = cats.get(i['category'], 0) + 1
for cat, cnt in sorted(cats.items()):
    print(f'  {cat}: {cnt}건')
"
```

Expected: 총 750건 (15카테고리 × 50개), 카테고리별 50건

- [ ] **Step 2: DB review_score 확인**

```bash
.venv/bin/python -c "
from src.models import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    rows = conn.execute(text(
        \"SELECT platform, COUNT(*), AVG(review_score) FROM ranking_snapshots \"
        \"WHERE review_score IS NOT NULL GROUP BY platform\"
    )).fetchall()
for r in rows:
    print(r)
"
```

Expected: `('musinsa', N, avg_score)` 행 출력

- [ ] **Step 3: 최종 커밋 (변경 없으면 skip)**

모든 테스트 통과 후 미커밋 파일 있으면:

```bash
git status
git add -p  # 필요한 파일만 선택
git commit -m "chore: 통합 검증 완료"
```
