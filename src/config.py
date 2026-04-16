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

# ── 무신사 URL ──
# categoryCode는 Stage 3에서 실제 탭 클릭으로 확정
MUSINSA_BASE = "https://www.musinsa.com/main/beauty/ranking?categoryCode={code}"
MUSINSA_URLS: list[tuple[str, str]] = [
    (MUSINSA_BASE.format(code="TBD_SKINCARE"), "skincare"),
    (MUSINSA_BASE.format(code="TBD_MAKEUP"),   "makeup"),
    (MUSINSA_BASE.format(code="TBD_SUNCARE"),  "suncare"),
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
