# beauty-ranking-crawler

올리브영·무신사 뷰티 제품 랭킹을 자동 수집하여 시계열 DB로 축적하는 크롤러입니다.

스킨케어·메이크업·선케어 카테고리별 TOP 50을 수집하고, 순위 변동·브랜드 점유율·할인율 등을 리포트로 출력합니다.

---

## 컨셉

뷰티 플랫폼의 랭킹은 매일 바뀝니다. 그런데 **"어떤 제품이 언제부터 순위에 올랐는지"**, **"어떤 브랜드가 꾸준히 상위권인지"**를 알려면 스냅샷을 직접 쌓아야 합니다.

이 프로그램은:

- 올리브영·무신사의 **랭킹 데이터를 자동 수집**해 순위를 긁어옵니다
- 수집할 때마다 **SQLite DB에 시점을 기록**해 누적합니다
- 쌓인 데이터로 **순위 변동·브랜드 점유율·가성비 리포트**를 뽑습니다

올리브영은 일반 HTTP 요청이 막혀 있어 [Scrapling](https://github.com/D4Vinci/Scrapling)의 스텔스 브라우저 자동화로 우회합니다. 무신사는 공개 랭킹 API를 `aiohttp`로 직접 호출합니다.

---

## 주요 기능

- **랭킹 수집**: 올리브영 3개 카테고리 × TOP 50, 무신사 15개 카테고리 × TOP 50
- **상세 보강**: 상품 상세 페이지에서 별점·리뷰수 추가 수집
- **시계열 저장**: 실행할 때마다 스냅샷을 SQLite에 누적
- **JSONL 백업**: 수집 회차별 원본 데이터 파일 자동 생성
- **리포트**: 순위 변동, 브랜드 점유율, 가성비 TOP N, 리뷰수 TOP N

---

## 수집 항목

| 항목 | 설명 |
|------|------|
| `rank` | 카테고리 내 순위 |
| `product_name` | 상품명 |
| `brand` | 브랜드명 |
| `original_price` | 정가 (원) |
| `sale_price` | 할인가 (원) |
| `discount_rate` | 할인율 (%) |
| `rating` | 별점 (0~5) — 올리브영만 수집 (상세 페이지 보강) |
| `review_score` | 리뷰 점수 (정수) — 무신사만 수집 (API 제공) |
| `review_count` | 리뷰 수 |
| `badge` | 랭킹 뱃지 (신상, 베스트 등) |
| `platform` | `oliveyoung` / `musinsa` |
| `category` | `skincare` / `makeup` / `suncare` |

---

## 기술 스택

| 역할 | 라이브러리 |
|------|-----------|
| 크롤링 엔진 | [Scrapling](https://github.com/D4Vinci/Scrapling) 0.4 — 스텔스 브라우저 자동화 + Smart Element Tracking |
| API 수집 | [aiohttp](https://github.com/aio-libs/aiohttp) — 무신사 랭킹 API 비동기 호출 |
| DB ORM | [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) 2.0 (SQLite) |
| 데이터 검증 | [Pydantic](https://github.com/pydantic/pydantic) 2.0 |
| 비동기 런타임 | [uvloop](https://github.com/MagicStack/uvloop) |
| 테스트 | [pytest](https://github.com/pytest-dev/pytest) |

---

## 프로젝트 구조

```
cosmetics_scraping/
├── src/
│   ├── config.py       # URL, 카테고리 코드, CLI 인자
│   ├── spider.py       # BeautyRankingSpider (수집 로직)
│   ├── parsers.py      # 가격·별점 파싱 함수
│   ├── musinsa_fetcher.py  # 무신사 랭킹 API 비동기 수집
│   ├── enricher.py     # 상세 페이지 rating/review_count 보강
│   ├── models.py       # SQLAlchemy 모델 + Pydantic 스키마
│   ├── storage.py      # DB 저장 로직
│   ├── report.py       # 리포트 생성
│   └── main.py         # 진입점
├── tests/              # pytest (32 tests)
├── data/
│   ├── beauty_ranking.db              # SQLite DB
│   ├── ranking_YYYYMMDD_HHMMSS.jsonl  # 회차별 JSONL 백업
│   └── crawl_state/                   # 중단 재개용 체크포인트
├── logs/
│   └── crawl.log
└── pyproject.toml
```

---

## 설치

```bash
git clone https://github.com/Chohangryong/cosmetics-scraping.git
cd cosmetics-scraping

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

> Python 3.10 이상 필요

---

## 사용법

### 기본 실행 (브라우저 창 표시)

```bash
python -m src.main
```

### 헤드리스 모드 (스케줄링·서버 실행용)

```bash
python -m src.main --headless
```

### 리포트 출력

수집 후 DB를 읽어 터미널에 출력하고 CSV로 저장합니다.

```bash
python -m src.report
```

출력 예시:
```
① 카테고리별 순위 변동 TOP 10
② 브랜드 점유율 (카테고리별)
③ 가성비 TOP 10 (리뷰수 가중)
④ 리뷰수 TOP 10
```

### 테스트

```bash
pytest                    # 유닛 테스트 (32개)
pytest -m live            # 실제 사이트 연결 테스트 (네트워크 필요)
```

---

## 출력 파일

| 파일 | 내용 |
|------|------|
| `data/beauty_ranking.db` | 누적 랭킹 DB (SQLite) |
| `data/ranking_YYYYMMDD_HHMMSS.jsonl` | 회차별 원본 데이터 |
| `data/report_YYYYMMDD_products.csv` | 상품별 리포트 |
| `data/report_YYYYMMDD_brands.csv` | 브랜드별 리포트 |
| `data/insight_YYYYMMDD_rank_change.csv` | 순위 변동 데이터 |
| `logs/crawl.log` | 수집 로그 |

---

## 현재 지원 범위

| 플랫폼 | 상태 |
|--------|------|
| 올리브영 (스킨케어·메이크업·선케어) | ✅ 운영 중 |
| 무신사뷰티 (15개 카테고리) | ✅ 운영 중 |
