import argparse

# ── 운영 모드 ──
# 첫 실행: False (auto_save로 지문 저장)
# 이후 실행: True (adaptive로 자동 탐색)
ADAPTIVE_MODE: bool = False

# ── CLI 인자 ──
def parse_args():
    parser = argparse.ArgumentParser(description="뷰티 랭킹 수집기")
    parser.add_argument("--headless", action="store_true", default=False,
                        help="브라우저를 헤드리스 모드로 실행 (스케줄링용)")
    return parser.parse_args()

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
