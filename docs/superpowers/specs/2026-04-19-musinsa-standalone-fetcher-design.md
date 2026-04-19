# 무신사 Standalone Fetcher 분리 설계

**날짜:** 2026-04-19  
**상태:** 승인됨  
**범위:** Stage 3 — 무신사 랭킹 수집 방식 전환

---

## 배경

현재 `BeautyRankingSpider`는 올리브영과 무신사를 동일한 Spider 세션(StealthyFetcher, 헤드리스 브라우저)으로 처리한다. 무신사 랭킹 페이지는 infinite scroll 방식이어서 브라우저 렌더링 후에도 24개만 수집되는 한계가 있다.

분석 결과, 무신사는 `api.musinsa.com/api2/hm/web/v5/pans/ranking/sections/231` API로 브라우저 없이 카테고리당 102개 상품 데이터를 직접 수집할 수 있음을 확인했다. rank, reviewScore, reviewCount까지 API 응답에 포함되어 있어 별도 enrich 없이 완전한 데이터 수집이 가능하다.

---

## 아키텍처

### 실행 흐름

```
main.py
├── BeautyRankingSpider.start()     → 올리브영 3카테고리 (기존 유지)
└── musinsa_fetcher.fetch_all()     → 무신사 15카테고리 (신규)
         ↓ aiohttp + Semaphore(3), 딜레이 2초
         sections API (브라우저 없음, curl 접근 가능 확인)

결과 합산 → JSONL 저장 → DB 저장 → enrich_ratings (올리브영만)
```

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `src/musinsa_fetcher.py` | 신규 — aiohttp 병렬 호출, JSON 파싱 |
| `src/models.py` | `review_score INTEGER` 컬럼 추가 + `migrate_db()` 반영 + `RankingItem`에 `review_score: int \| None` 필드 추가 |
| `src/spider.py` | musinsa session 제거, `start_requests`에서 무신사 제거 |
| `src/config.py` | `MUSINSA_URLS` → `MUSINSA_CATEGORY_CODES: list[tuple[str, str]]` 재정의 |
| `src/main.py` | `musinsa_fetcher.fetch_all()` 호출 + 결과 합산 로직 추가 |

---

## 상세 설계

### sections API

```
GET https://api.musinsa.com/api2/hm/web/v5/pans/ranking/sections/231
    ?storeCode=beauty&gf=A&categoryCode={code}&page=1

Headers:
  User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
  Accept: application/json
  Referer: https://www.musinsa.com/main/beauty/ranking
```

응답 구조: `data.modules[1..17]` 각각 `items` 6개 (총 102개/카테고리)

### 필드 매핑

| RankingItem 필드 | API 경로 | 비고 |
|---|---|---|
| `product_id` | `item.id` | |
| `rank` | `item.image.rank` | API 직접 제공, 1-based |
| `brand` | `item.info.brandName` | |
| `name` | `item.info.productName` | |
| `sale_price` | `item.info.finalPrice` | 쿠폰 포함 최저가 |
| `original_price` | `onClick.eventLog.ga4.payload.original_price` | 정가 |
| `discount_rate` | `item.info.discountRatio` | finalPrice 기준 할인율 |
| `badge` | `onClick.eventLog.ga4.payload.item_flag` | `"none"` → `""` 변환 |
| `review_score` | `onClick.eventLog.amplitude.payload.reviewScore` | 0-100, 무신사 전용 신규 컬럼 |
| `review_count` | `onClick.eventLog.amplitude.payload.reviewCount` | str → int 변환 |
| `rating` | — | 무신사는 NULL (올리브영 전용 유지) |

**수집 범위:** 102개 중 rank 1~50만 사용

### musinsa_fetcher.py 구조

```python
API_URL = "https://api.musinsa.com/api2/hm/web/v5/pans/ranking/sections/231"
MUSINSA_CONCURRENCY = 3   # Semaphore
MUSINSA_API_DELAY = 2.0   # 초, 카테고리 요청 간 딜레이

async def fetch_category(session, code, category, semaphore, max_rank=50) -> list[dict]:
    async with semaphore:
        async with session.get(API_URL, params={...}, headers=HEADERS) as resp:
            data = await resp.json()
        await asyncio.sleep(MUSINSA_API_DELAY)
    # modules 순회 → PRODUCT_COLUMN items 추출 → rank <= max_rank 필터
    # 파싱 후 list[dict] 반환

async def fetch_all(category_codes: list[tuple[str, str]], max_rank: int = 50) -> list[dict]:
    semaphore = asyncio.Semaphore(MUSINSA_CONCURRENCY)
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_category(session, code, cat, semaphore, max_rank)
                 for code, cat in category_codes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    # 에러 건은 카테고리명과 함께 ERROR 로깅 후 skip
    return [item for sublist in results if isinstance(sublist, list) for item in sublist]
```

### DB 스키마 변경

```sql
-- ranking_snapshots에 컬럼 추가
ALTER TABLE ranking_snapshots ADD COLUMN review_score INTEGER;
-- 기존 rating FLOAT 유지 (올리브영용 0-5 별점)
```

`migrate_db()`에 `"review_score INTEGER"` 추가 (idempotent, 이미 있으면 무시).

### config.py 변경

```python
# 기존 MUSINSA_URLS (URL 문자열) 제거
# 신규
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

### main.py 변경

```python
spider = BeautyRankingSpider(headless=args.headless, crawldir="data/crawl_state")
spider_result = spider.start(use_uvloop=True)

musinsa_items = asyncio.run(musinsa_fetcher.fetch_all(MUSINSA_CATEGORY_CODES))

all_items = list(spider_result.items) + musinsa_items
# 이후 JSONL 저장, DB 저장, enrich_ratings(올리브영만) 동일
```

---

## 에러 처리

| 상황 | 처리 방식 |
|---|---|
| 카테고리 API 호출 실패 | 해당 카테고리 ERROR 로깅 후 skip (전체 중단 없음) |
| reviewScore/reviewCount 누락 | None으로 저장 |
| rank > 50 | 파싱 단계에서 조기 종료 |
| HTTP 4xx/5xx | `return_exceptions=True`로 포착, 로깅 후 빈 리스트 처리 |

---

## 동시성/딜레이 정책

| 항목 | 값 | 근거 |
|---|---|---|
| `MUSINSA_CONCURRENCY` | 3 | Spider HTML 크롤과 동일 기준 |
| `MUSINSA_API_DELAY` | 2초 | API이므로 HTML 크롤(20초) 대비 완화 |

---

## 테스트 계획

1. `fetch_category` 단위 테스트: 실제 API 1개 카테고리 호출 → 50개 반환 확인
2. 필드 파싱 검증: `review_score`, `review_count`, `badge("none"→"")` 변환
3. 통합 실행: `python -m src.main` → `ms_count >= 50*15` 확인
4. DB 확인: `review_score` 컬럼 정상 저장 여부
