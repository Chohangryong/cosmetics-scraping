# 뷰티 제품 랭킹 수집 에이전트 시스템 설계서

> **버전**: v3.1  
> **작성일**: 2026-04-15  
> **변경 이력**:  
> - v3.0 → v3.1 Scrapling 0.4 공식 API 기반 API 시그니처 검증 완료. 놓친 부가 기능(`disable_resources`, `blocked_domains`, `robots_txt_obey`, `use_uvloop`, Development Mode, Streaming 모드) 추가  
> - v3.0 주요 오류 수정: `configure_sessions()` 메서드 방식, `AsyncStealthySession` 사용 (Spider async 요구), `concurrent_requests` 속성명, `crawldir`은 생성자 파라미터
>
> **목적**: Claude Code 구현 참조용 계획서  
> **기반 라이브러리**: Scrapling 0.4 (2026-02 기준)

---

## 1. 작업 컨텍스트

### 1.1 배경 및 목적

올리브영과 무신사뷰티의 뷰티 제품 랭킹을 자동으로 수집하여 시계열 데이터로 축적한다. [Scrapling](https://github.com/D4Vinci/Scrapling) 프레임워크를 크롤링 엔진으로 사용하며, Scrapling이 제공하는 기능을 **최대한 활용**하여 자체 구현을 최소화한다.

> **네이버쇼핑 제외**: 2026-04 기준 뷰티 랭킹 페이지 폐지 확인. Phase 2에서 추가.

### 1.2 범위

| 항목 | 내용 |
|------|------|
| 플랫폼 | 올리브영, 무신사뷰티 |
| 카테고리 | 스킨케어, 메이크업, 선케어 |
| 수집 깊이 | 카테고리당 TOP 50 |
| 수집 항목 | 순위, 상품명, 브랜드, 정가, 할인가, 별점, 상품ID, 뱃지 |
| 실행 환경 | 로컬 PC (상시 가동) |

### 1.3 제약조건

- 올리브영: requests → 403 차단. 브라우저 자동화 필수
- 무신사: CSR 렌더링. JavaScript 실행 필수. `Crawl-delay: 60` 권고
- 두 사이트 모두 `robots.txt`에서 일반 봇 `Disallow: /`
- **정책 결정**: 개인 분석 용도, 저빈도 수집이므로 `robots_txt_obey=False`로 설정하되 `download_delay`로 예의를 지킴

---

## 2. Scrapling 0.4 기능 매핑

### 2.1 활용 매핑 (전체 체크리스트)

| Scrapling 기능 | 우리 시스템 활용 | 비고 |
|--------------|----------------|------|
| **Spider 프레임워크** | ✅ BeautyRankingSpider가 상속 | 핵심 |
| **`configure_sessions(manager)`** | ✅ 플랫폼별 세션 분리 | Multi-Session |
| **`AsyncStealthySession`** | ✅ 두 플랫폼 모두 사용 | Spider는 async이므로 Async 버전 필수 |
| **`concurrent_requests`** | ✅ = 1 (순차 실행) | 정확한 속성명 |
| **`download_delay`** | ✅ = 20 (기본 딜레이) | |
| **`max_blocked_retries`** | ✅ = 3 | 차단 시 재시도 |
| **`robots_txt_obey`** | ✅ = False (명시) | 정책 결정 반영 |
| **`is_blocked()` 오버라이드** | ✅ "정상 동작하지 않습니다" 감지 | 커스텀 차단 판별 |
| **`crawldir` (생성자)** | ✅ "data/crawl_state" | 중단/재개 |
| **`spider.start(use_uvloop=True)`** | ✅ | async 성능 개선 |
| **`result.items.to_jsonl()`** | ✅ JSON 백업 | 스트리밍 친화적 |
| **`result.stats` (CrawlStats)** | ✅ 통계 로깅 | 요청수/실패/성공 |
| **`response.follow()`** | Phase 2 | 개별 상품 페이지 이동 |
| **`stream()` 모드** | 선택 (실시간 DB 저장용) | 아래 2.3절 참조 |
| **CSS/XPath 파서** | ✅ | |
| **`auto_save` / `adaptive`** | ✅ 모든 셀렉터에 적용 | Smart Element Tracking |
| **`disable_resources=True`** | ✅ (StealthySession) | **25% 속도 개선** (텍스트만 필요) |
| **`blocked_domains`** | ✅ 광고/트래커 차단 | 속도·안정성 개선 |
| **`network_idle=True`** | ✅ | JS 로딩 완료 대기 |
| **`wait_selector`** | ✅ 상품 목록 로딩 확인 | 파싱 전 확실한 대기 |
| **`hide_canvas=True`** | ✅ 캔버스 핑거프린팅 차단 | 스텔스 강화 |
| **`block_webrtc=True`** | ✅ WebRTC IP 누출 차단 | 스텔스 강화 |
| **`google_search=True`** (default) | ✅ | Google 검색 referer 위장 |
| **`solve_cloudflare=False`** (default) | ✅ | 두 사이트 모두 CF 없음 → 불필요 |
| **`timeout=60000`** (ms) | ✅ | 무신사 SPA 로딩 대비 |
| **Development Mode** | 개발 시 사용 | `cache_responses=True` 옵션 |
| **ProxyRotator** | Phase 2 | IP 차단 대응 |
| **`scrapling` CLI** | 개발 시 빠른 테스트 | `scrapling extract stealthy-fetch` |

### 2.2 우리가 직접 구현하는 것 (최소)

Spider가 `yield dict`한 결과를 DB에 저장하는 것과 설정값 정의만 우리 몫.

- `config.py`: URL, 카테고리 코드, ADAPTIVE_MODE, 광고 차단 도메인 목록
- `spider.py`: BeautyRankingSpider (Scrapling Spider 상속)
- `parsers.py`: parse_price, parse_rating 등 순수 파싱 함수
- `models.py`: SQLAlchemy + Pydantic
- `storage.py`: Spider 결과 → DB 저장
- OS crontab/launchd: 하루 2회 실행 트리거

### 2.3 실행 방식 2안 비교: `start()` vs `stream()`

Scrapling은 두 가지 실행 방식을 제공한다. 우리는 **start() 방식**을 선택한다.

| 방식 | 특징 | 우리 적합성 |
|------|------|-----------|
| `result = spider.start()` | 크롤 완료 후 전체 결과 반환 | **✅ 채택** — 완료 후 DB 일괄 저장 |
| `async for item in spider.stream()` | 아이템을 실시간 yield | 데이터 규모 300건 → 실시간 저장 이점 작음 |

---

## 3. Spider 구현 설계 (API 검증 완료)

### 3.1 BeautyRankingSpider 전체 구조

```python
from scrapling.spiders import Spider, Request, Response
from scrapling.fetchers import AsyncStealthySession
from config import (
    OLIVEYOUNG_URLS, MUSINSA_URLS,
    ADAPTIVE_MODE, BLOCKED_DOMAINS,
)


class BeautyRankingSpider(Spider):
    name = "beauty_ranking"

    # ── Spider 클래스 속성 (Scrapling 공식 API) ──
    start_urls: list[str] = []   # start_requests()에서 동적 생성

    concurrent_requests: int = 1          # 동시 요청 수 (순차 실행)
    download_delay: int = 20               # 기본 요청 간 딜레이 (초)
    max_blocked_retries: int = 3           # 차단 시 재시도 횟수
    robots_txt_obey: bool = False          # robots.txt 무시 (정책 결정, 2.1절 참조)

    # ── Multi-Session 설정 (Scrapling 공식 API: configure_sessions) ──
    def configure_sessions(self, manager):
        """플랫폼별 AsyncStealthySession 등록.
        Spider가 async이므로 반드시 Async 버전을 사용한다.
        """
        # 올리브영: 봇 차단 강함 → lazy=False (시작 시 즉시 초기화)
        manager.add(
            "oliveyoung",
            AsyncStealthySession(
                headless=False,                # 실제 크롬 창 표시 (탐지 최소화)
                network_idle=True,             # JS 로딩 완료까지 대기
                disable_resources=True,        # 이미지/폰트/미디어 차단 → 25% 속도↑
                blocked_domains=BLOCKED_DOMAINS,
                hide_canvas=True,              # Canvas 핑거프린팅 차단
                block_webrtc=True,             # WebRTC IP 누출 차단
                timeout=60000,                 # 60초 (밀리초 단위)
                google_search=True,            # Google referer 위장 (기본값)
                solve_cloudflare=False,        # 올리브영은 CF 없음
            ),
            lazy=False,
        )
        # 무신사: CSR이지만 봇 차단 약함 → lazy=True (첫 사용 시 초기화)
        manager.add(
            "musinsa",
            AsyncStealthySession(
                headless=False,
                network_idle=True,
                disable_resources=True,
                blocked_domains=BLOCKED_DOMAINS,
                hide_canvas=True,
                block_webrtc=True,
                timeout=60000,
                google_search=True,
                solve_cloudflare=False,
            ),
            lazy=True,
        )

    # ── 시작 요청 생성 ──
    def start_requests(self):
        """URL별로 세션(sid)과 메타데이터 지정하여 Request 생성."""
        for url, category in OLIVEYOUNG_URLS:
            yield Request(
                url=url,
                callback=self.parse_oliveyoung,
                sid="oliveyoung",
                meta={"platform": "oliveyoung", "category": category},
            )
        for url, category in MUSINSA_URLS:
            yield Request(
                url=url,
                callback=self.parse_musinsa,
                sid="musinsa",
                meta={"platform": "musinsa", "category": category},
            )

    # ── 파싱 콜백 (플랫폼별 분리) ──
    async def parse_oliveyoung(self, response: Response):
        """올리브영 TOP 50 파싱."""
        use_adaptive = ADAPTIVE_MODE
        items = response.css(
            'ul.cate_prd_list > li',
            auto_save=not use_adaptive,
            adaptive=use_adaptive,
        )

        # Adaptive 폴백: 0건이면 지문 갱신 시도
        if not items and use_adaptive:
            items = response.css('ul.cate_prd_list > li', auto_save=True)

        for item in items[:50]:
            a_tag = item.css_first('a[data-ref-goodsno]')
            if not a_tag:
                continue
            yield {
                "platform": "oliveyoung",
                "category": response.meta["category"],
                "product_id": a_tag.attrib.get('data-ref-goodsno', ''),
                "rank": parse_rank_from_data_attr(a_tag.attrib.get('data-attr', '')),
                "brand":  (item.css_first('.tx_brand').text or '').strip(),
                "name":   (item.css_first('.tx_name').text or '').strip(),
                "sale_price":     parse_price(item.css_first('.tx_cur .tx_num').text),
                "original_price": parse_price(item.css_first('.tx_org .tx_num').text),
                "rating":         parse_rating(item.css_first('.point').text),
                "badge": extract_badges(item),
            }

    async def parse_musinsa(self, response: Response):
        """무신사 TOP 50 파싱 (data 속성 기반)."""
        use_adaptive = ADAPTIVE_MODE
        cards = response.css(
            'div[class*="UIProductColumn__Wrap"]',
            auto_save=not use_adaptive,
            adaptive=use_adaptive,
        )

        if not cards and use_adaptive:
            cards = response.css('div[class*="UIProductColumn__Wrap"]', auto_save=True)

        for card in cards[:50]:
            yield {
                "platform": "musinsa",
                "category": response.meta["category"],
                "product_id":     card.attrib.get('data-item-id', ''),
                "rank":           int(card.attrib.get('data-index', 0)),
                "brand":          card.attrib.get('data-item-brand', ''),
                "name":           extract_musinsa_product_name(card),
                "original_price": int(card.attrib.get('data-original-price', 0) or 0),
                "sale_price":     int(card.attrib.get('data-best-price', 0) or 0),
                "discount_rate":  int(card.attrib.get('data-discount-rate', 0) or 0),
                "badge":          card.attrib.get('data-item-flag', ''),
                "rating":         None,  # 무신사 랭킹 목록에 별점 미표시
            }

    # ── 차단 감지 커스터마이즈 ──
    def is_blocked(self, response: Response) -> bool:
        """올리브영 봇 차단 메시지 및 HTTP 오류 감지."""
        if response.status and response.status >= 400:
            return True
        body = (response.text or '')
        if "정상 동작하지 않습니다" in body:
            return True  # 올리브영 봇 차단 문구
        return False
```

### 3.2 파싱 유틸리티 (`parsers.py`)

```python
import re


def parse_price(text: str | None) -> int | None:
    """'21,900' → 21900"""
    if not text:
        return None
    clean = text.replace(',', '').replace('원', '').strip()
    return int(clean) if clean.isdigit() else None


def parse_rating(text: str | None) -> float | None:
    """'10점만점에 5.5점' → 5.5"""
    if not text:
        return None
    match = re.search(r'(\d+\.?\d*)점$', text)
    return float(match.group(1)) if match else None


def parse_rank_from_data_attr(data_attr: str) -> int:
    """'랭킹^판매랭킹리스트_스킨케어^[상품명]^1' → 1"""
    try:
        return int(data_attr.split('^')[-1])
    except (ValueError, IndexError):
        return 0


def extract_badges(item) -> str:
    """올리브영 뱃지 목록 추출 (세일/쿠폰/증정/오늘드림)"""
    flags = item.css('.icon_flag')
    return ','.join(f.text.strip() for f in flags if f.text) if flags else ''


def extract_musinsa_product_name(card) -> str:
    """무신사 innerText에서 브랜드 다음 줄이 상품명"""
    lines = [l.strip() for l in (card.text or '').split('\n') if l.strip()]
    brand = card.attrib.get('data-item-brand', '')
    for i, line in enumerate(lines):
        if brand and brand.lower() in line.lower() and i + 1 < len(lines):
            return lines[i + 1]
    return lines[3] if len(lines) > 3 else ''
```

### 3.3 진입점 (`main.py`)

```python
from spider import BeautyRankingSpider
from storage import save_to_db
from datetime import datetime
import logging

log = logging.getLogger(__name__)


def main():
    # crawldir은 Spider 생성자에 전달 (Ctrl+C → 재실행 시 이어서)
    spider = BeautyRankingSpider(crawldir="data/crawl_state")

    # use_uvloop: async 성능 개선 (uvloop 설치 시 자동 활용)
    result = spider.start(use_uvloop=True)

    # 1. JSON 백업 (Scrapling 내장 Export)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result.items.to_jsonl(f"data/ranking_{timestamp}.jsonl")

    # 2. DB 저장 (우리가 구현하는 유일한 저장 로직)
    save_to_db(result.items)

    # 3. 통계 출력 (Scrapling CrawlStats)
    log.info(f"총 수집: {len(result.items)}")
    log.info(f"통계: {result.stats}")


if __name__ == "__main__":
    main()
```

### 3.4 설정 (`config.py`)

```python
# ── 운영 모드 ──
# 첫 실행: False (auto_save로 지문 저장)
# 이후 실행: True (adaptive로 자동 탐색)
ADAPTIVE_MODE: bool = True

# ── 올리브영 URL ──
OLIVEYOUNG_BASE = (
    "https://www.oliveyoung.co.kr/store/main/getBestList.do"
    "?dispCatNo=900000100100001&fltDispCatNo={code}"
)
OLIVEYOUNG_URLS: list[tuple[str, str]] = [
    (OLIVEYOUNG_BASE.format(code="10000010001"), "skincare"),
    (OLIVEYOUNG_BASE.format(code="10000010002"), "makeup"),
    (OLIVEYOUNG_BASE.format(code="10000010011"), "suncare"),
]

# ── 무신사 URL ──
# categoryCode는 Stage 3에서 실제 탭 클릭으로 확정
MUSINSA_BASE = "https://www.musinsa.com/main/beauty/ranking?categoryCode={code}"
MUSINSA_URLS: list[tuple[str, str]] = [
    (MUSINSA_BASE.format(code="TBD_SKINCARE"), "skincare"),
    (MUSINSA_BASE.format(code="TBD_MAKEUP"),   "makeup"),
    (MUSINSA_BASE.format(code="TBD_SUNCARE"),  "suncare"),
]

# ── 차단할 광고/트래커 도메인 (Scrapling blocked_domains) ──
BLOCKED_DOMAINS: set[str] = {
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.net",
    "criteo.com",
    "amazon-adsystem.com",
}
```

---

## 4. 사이트별 실측 데이터 (DOM 분석 결과)

### 4.1 올리브영 (실측 완료 ✅)

| 항목 | 확정값 |
|------|-------|
| 기본 URL | `https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo={코드}` |
| 카테고리: 스킨케어 | `10000010001` |
| 카테고리: 메이크업 | `10000010002` |
| 카테고리: 선케어 | `10000010011` |
| 상품 목록 셀렉터 | `ul.cate_prd_list > li` (100개 로딩 확인) |
| 상품 ID | `a[data-ref-goodsno]` → `"A000000250474"` |
| 랭킹 순위 | `a[data-attr]` → `"^1"` (마지막 `^` 뒤 숫자) |
| 브랜드 | `.tx_brand` → `"에스네이처"` |
| 상품명 | `.tx_name` |
| 할인가 | `.tx_cur .tx_num` → `"21,900"` |
| 정가 | `.tx_org .tx_num` → `"43,000"` |
| 별점 | `.point` → `"10점만점에 5.5점"` |
| 봇 차단 메시지 | `"정상 동작하지 않습니다"` (is_blocked 판별용) |

### 4.2 무신사뷰티 (실측 완료 ✅)

| 항목 | 확정값 |
|------|-------|
| 기본 URL | `https://www.musinsa.com/main/beauty/ranking?categoryCode={코드}` |
| 전체 카테고리 | `104000` (실측 확인) |
| 스킨케어/메이크업/선케어 | Stage 3에서 탭 클릭 후 확정 |
| 상품 카드 셀렉터 | `div[class*="UIProductColumn__Wrap"]` (93개 로딩 확인) |
| 상품 ID | `data-item-id` → `"6056293"` |
| 랭킹 순위 | `data-index` → `"1"` |
| 브랜드 | `data-item-brand` → `"athanbe"` |
| 정가 | `data-original-price` → `"105000"` |
| 할인가 | `data-best-price` → `"49140"` |
| 할인율 | `data-discount-rate` → `"40"` |
| 뱃지 | `data-item-flag` → `"급상승 라벨"` |
| 상품명 | innerText 파싱 (브랜드 다음 줄) |
| 별점 | 랭킹 목록에 미표시 → NULL |

---

## 5. Adaptive 셀렉터 전략

### 5.1 운영 모드

```
[첫 실행 (INIT)]                                [이후 실행 (ADAPTIVE)]
ADAPTIVE_MODE = False                           ADAPTIVE_MODE = True
     │                                               │
     ▼                                               ▼
auto_save=True                                  adaptive=True
→ 요소 지문 저장                                  → 저장된 지문으로 유사 요소 자동 탐색
                                                     │
                                         ┌───────────┴───────────┐
                                         │                       │
                                    결과 > 0건              결과 = 0건
                                         │                       │
                                         ▼                       ▼
                                    정상 저장           auto_save=True 폴백
                                                         (지문 갱신)
                                                               │
                                                 ┌─────────────┴─────────────┐
                                                 │                           │
                                            성공                        실패 → 에러 로그
                                                                      (사이트 대규모 리뉴얼 추정)
```

### 5.2 구현 위치

- `config.py`의 `ADAPTIVE_MODE` 플래그
- `spider.py`의 `parse_oliveyoung()`, `parse_musinsa()`에서 플래그 참조
- 폴백 로직은 각 parse 콜백 안에 포함 (상위 3.1절 코드 참조)

---

## 6. DB 설계

Scrapling이 JSONL로 원본을 백업하고, SQLite에 정규화된 형태로 저장한다.

```sql
CREATE TABLE products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    product_id      TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    brand           TEXT,
    first_seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, product_id)
);

CREATE TABLE ranking_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    platform        TEXT NOT NULL,
    category        TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    original_price  INTEGER,
    sale_price      INTEGER,
    discount_rate   INTEGER,
    rating          REAL,
    badge           TEXT,
    collected_at    TIMESTAMP NOT NULL
);

CREATE INDEX idx_snapshots_lookup ON ranking_snapshots(platform, category, collected_at);
CREATE INDEX idx_snapshots_product ON ranking_snapshots(product_id, collected_at);
CREATE INDEX idx_products_platform ON products(platform, product_id);
```

---

## 7. 스케줄링

APScheduler를 쓰지 않는다. **OS 기본 스케줄러**를 사용한다.

### 7.1 Mac (launchd)

`~/Library/LaunchAgents/com.beauty-ranking.plist`:
```xml
<plist version="1.0">
<dict>
    <key>Label</key><string>com.beauty-ranking</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>src.main</string>
    </array>
    <key>WorkingDirectory</key><string>/path/to/beauty-ranking-crawler</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    </array>
</dict>
</plist>
```

등록: `launchctl load ~/Library/LaunchAgents/com.beauty-ranking.plist`

### 7.2 Windows (작업 스케줄러)

```bat
schtasks /create /tn "BeautyRanking_AM" /tr "python -m src.main" /sc daily /st 09:00
schtasks /create /tn "BeautyRanking_PM" /tr "python -m src.main" /sc daily /st 21:00
```

### 7.3 타이밍

- `concurrent_requests=1` + `download_delay=20`: 요청 간 최소 20초
- 무신사 `Crawl-delay: 60` 준수 → 무신사 세션 요청 시 추가 대기 (start_requests priority로 제어 or 무신사만 별도 download_delay)
- 예상 총 소요시간: **약 10~12분**

> **미해결 이슈**: 도메인별 download_delay 차등 설정은 Scrapy와 달리 Scrapling 문서에 명확한 방법이 없음. 해결책 2가지:
> 1. `concurrent_requests=1`로 두고, 무신사 3건 수집 후 **별도 asyncio.sleep** 삽입 (parse 콜백에서)
> 2. 기본 `download_delay=60`으로 설정하여 모든 요청에 60초 적용 (안전하지만 총 시간↑)
> → Stage 3에서 실제 테스트로 결정

---

## 8. 폴더 구조 & 의존성

### 8.1 폴더

```
beauty-ranking-crawler/
├── CLAUDE.md                     # Claude Code 구현 지침
├── DESIGN.md                     # 본 설계서
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py                   # 진입점
│   ├── config.py                 # URL, 카테고리 코드, ADAPTIVE_MODE, BLOCKED_DOMAINS
│   ├── spider.py                 # BeautyRankingSpider (Scrapling Spider 상속)
│   ├── parsers.py                # parse_price, parse_rating, extract_* 유틸
│   ├── models.py                 # SQLAlchemy ORM + Pydantic
│   └── storage.py                # DB 저장
├── data/
│   ├── beauty_ranking.db         # 수집 데이터
│   ├── crawl_state/              # Scrapling pause/resume 체크포인트
│   └── ranking_*.jsonl           # JSONL 백업
└── logs/
    └── crawl.log
```

### 8.2 의존성

```toml
[project]
requires-python = ">=3.10"
dependencies = [
    "scrapling>=0.4",      # 크롤링 엔진 전체 (Fetcher + Spider + Parser + 모든 기능)
    "sqlalchemy>=2.0",     # DB ORM
    "pydantic>=2.0",       # 데이터 검증
    "uvloop; sys_platform != 'win32'",   # Spider async 성능 개선 (Windows 제외)
]
```

설치:
```bash
pip install -e .
scrapling install    # Playwright/patchright 브라우저 다운로드
```

**APScheduler 제거됨**: OS crontab/launchd로 대체.  
**우리 직접 구현하는 의존성**: SQLAlchemy(DB), Pydantic(검증) 2가지만.  
**나머지 모든 크롤링 기능**: Scrapling에 완전히 위임.

---

## 9. 구현 단계 (Claude Code 순차 실행)

### Stage 1: 프로젝트 초기화
- pyproject.toml, 폴더 구조 생성
- `pip install -e . && scrapling install`
- config.py, models.py, storage.py 구현
- **검증**: DB 생성, 테이블 확인

### Stage 2: Spider 골격 + 올리브영 파싱
- spider.py: BeautyRankingSpider (올리브영만 먼저)
- parsers.py: parse_price, parse_rating, extract_badges
- main.py: Spider 실행 + JSONL/DB 저장
- `ADAPTIVE_MODE = False`로 첫 실행 (auto_save 지문 저장)
- **검증**: 스킨케어 TOP 50 수집 → JSONL/DB 조회 확인, auto_save 지문 생성 확인

### Stage 3: 무신사 파싱 추가
- spider.py에 parse_musinsa 추가
- **카테고리 탭 클릭으로 categoryCode 확정** → config.py 갱신
- 도메인별 딜레이 전략 테스트 (7.3절 2가지 안 중 결정)
- **검증**: 무신사 TOP 50 수집 → DB 확인

### Stage 4: 안정화 + 스케줄링
- `ADAPTIVE_MODE = True`로 전환
- `is_blocked()` 동작 테스트 (의도적 차단 시뮬레이션)
- `crawldir` pause/resume 테스트 (Ctrl+C → 재실행)
- OS crontab/launchd 등록
- 연속 실행 테스트 (2~3회)
- **검증**: adaptive 동작, CrawlStats 통계, 로그 확인

---

## 10. 개발 효율화 팁 (Scrapling CLI 활용)

Scrapling CLI로 개발 중 빠른 테스트:

```bash
# 올리브영 페이지 수집 + CSS로 추출 테스트
scrapling extract stealthy-fetch \
  'https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=10000010001' \
  output.html \
  --block-webrtc --hide-canvas --disable-resources --network-idle

# Python shell 인터랙티브 모드
scrapling shell
```

---

## 11. 미확인 사항

| 항목 | 확인 시점 | 비고 |
|------|----------|------|
| 무신사 스킨케어/메이크업/선케어 categoryCode | Stage 3 | 탭 클릭으로 실측 |
| AsyncStealthySession의 올리브영 403 우회 여부 | Stage 2 | 실제 실행 테스트 |
| 도메인별 download_delay 차등 설정 방법 | Stage 3 | 7.3절 2가지 안 중 결정 |
| Scrapling auto_save 지문 저장 위치/파일 | Stage 2 | 문서 미명시, 실측 확인 |
| `wait_selector` 올리브영 `.cate_prd_list` 대기 효과 | Stage 2 | 파싱 안정성 개선 확인 |

---

## 12. 향후 확장 (Phase 2)

| 항목 | Scrapling 활용 방식 |
|------|-------------------|
| 네이버쇼핑 추가 | `configure_sessions`에 "naver" AsyncStealthySession 추가 |
| 개별 상품 상세 수집 | parse 콜백에서 `response.follow(product_url, callback=self.parse_detail)` |
| IP 차단 대응 | Scrapling `ProxyRotator` 내장 기능 |
| DNS 누출 방지 | `dns_over_https=True` 옵션 |
| 대시보드 | Streamlit + SQLite 조회 |
| 알림 | Slack/Discord 웹훅 (랭킹 급변동 감지) |
| 개발 모드 재파싱 | `cache_responses=True`로 페이지 캐시 후 parse 로직만 반복 테스트 |
