import argparse

# ── 운영 모드 ──
# 첫 실행: False (auto_save로 지문 저장)
# 이후 실행: True (adaptive로 자동 탐색)
ADAPTIVE_MODE: bool = False

# ── CLI 인자 ──
PLATFORM_CHOICES = ("oliveyoung", "musinsa", "hwahae")


def parse_args():
    parser = argparse.ArgumentParser(description="뷰티 랭킹 수집기")
    parser.add_argument("--headless", action="store_true", default=False,
                        help="브라우저를 헤드리스 모드로 실행 (스케줄링용)")
    parser.add_argument("--platforms", default=",".join(PLATFORM_CHOICES),
                        help=f"수집 대상 (콤마 구분). 선택지: {','.join(PLATFORM_CHOICES)}. 예: --platforms hwahae")
    parser.add_argument("--hwahae-scope", choices=["a", "b"], default="b",
                        help="화해 수집 범위: a=depth-2(13개), b=depth-2+depth-3(117개)")
    parser.add_argument("--enrich-ingredients", action="store_true", default=False,
                        help="화해 성분 정보 enrich (concurrency 4, 화해 제품당 1 호출)")
    parser.add_argument("--enrich-effects", action="store_true", default=False,
                        help="화해 AI 효능 분석 enrich (concurrency 4, 화해 제품당 1 호출)")
    args = parser.parse_args()
    args.platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    invalid = [p for p in args.platforms if p not in PLATFORM_CHOICES]
    if invalid:
        parser.error(f"unknown platform: {invalid} (choices: {PLATFORM_CHOICES})")
    return args

# ── 올리브영 URL ──
OLIVEYOUNG_BASE = (
    "https://www.oliveyoung.co.kr/store/main/getBestList.do"
    "?dispCatNo=900000100100001&fltDispCatNo={code}"
)
OLIVEYOUNG_URLS: list[tuple[str, str]] = [
    (OLIVEYOUNG_BASE.format(code="10000010001"), "skincare"),
    (OLIVEYOUNG_BASE.format(code="10000010009"), "mask_pack"),
    (OLIVEYOUNG_BASE.format(code="10000010010"), "cleansing"),
    (OLIVEYOUNG_BASE.format(code="10000010011"), "suncare"),
    (OLIVEYOUNG_BASE.format(code="10000010002"), "makeup"),
    (OLIVEYOUNG_BASE.format(code="10000010012"), "nail"),
    (OLIVEYOUNG_BASE.format(code="10000010006"), "makeup_tool"),
    (OLIVEYOUNG_BASE.format(code="10000010008"), "dermo_cosmetics"),
    (OLIVEYOUNG_BASE.format(code="10000010007"), "mens_edit"),
    (OLIVEYOUNG_BASE.format(code="10000010005"), "fragrance"),
    (OLIVEYOUNG_BASE.format(code="10000010004"), "hair_care"),
    (OLIVEYOUNG_BASE.format(code="10000010003"), "body_care"),
    (OLIVEYOUNG_BASE.format(code="10000020004"), "hygiene"),
]

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

# ── 차단할 광고/트래커 도메인 ──
BLOCKED_DOMAINS: set[str] = {
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.net",
    "criteo.com",
    "amazon-adsystem.com",
}
