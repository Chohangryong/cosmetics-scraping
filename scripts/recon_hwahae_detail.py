"""화해 product detail endpoint 정찰.

product_id 1개로 detail 페이지를 방문해 XHR 캡처 → 성분(ingredient) 필드 위치 파악.
"""
import json
import logging
from pathlib import Path

from scrapling.fetchers import DynamicSession

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUT = Path("data/_recon/hwahae_detail.json")
PRODUCT_ID = "11414"  # 폰즈 메이크업 리무버
TARGET = f"https://www.hwahae.co.kr/products/{PRODUCT_ID}"
GATEWAY_RE = r"gateway\.hwahae\.co\.kr/.*"


def _scroll(page):
    for _ in range(3):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(800)
    return page


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with DynamicSession(capture_xhr=GATEWAY_RE, headless=True) as s:
        # 1단계: ranking 페이지 방문해서 쿠키/토큰 획득
        log.info("step 1: warm-up ranking page")
        s.fetch("https://www.hwahae.co.kr/rankings", network_idle=True, wait=2000)
        # 2단계: 같은 세션에서 product detail 이동
        log.info(f"step 2: product detail {TARGET}")
        page = s.fetch(TARGET, network_idle=True, page_action=_scroll, wait=3000)
        log.info(f"detail status: {getattr(page, 'status', '?')}")

    captured = []
    for x in page.captured_xhr:
        item = {"url": x.url, "status": x.status, "method": getattr(x, "method", "GET")}
        body = getattr(x, "body", None) or getattr(x, "text", None)
        if body:
            try:
                parsed = json.loads(body) if isinstance(body, str) else body
                # 성분 관련 키 탐지
                hint = []
                def scan(o, path=""):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            kl = str(k).lower()
                            if any(x in kl for x in ["ingredient", "ewg", "성분", "component"]):
                                hint.append(f"{path}.{k}")
                            scan(v, f"{path}.{k}")
                    elif isinstance(o, list) and o:
                        scan(o[0], f"{path}[0]")
                scan(parsed)
                item["ingredient_hints"] = hint[:20]
                # body 일부 저장
                item["body_preview"] = json.dumps(parsed, ensure_ascii=False)[:1500]
            except Exception as e:
                item["parse_error"] = str(e)
        captured.append(item)

    OUT.write_text(json.dumps({
        "target": TARGET,
        "product_id": PRODUCT_ID,
        "captured_xhr": captured,
    }, ensure_ascii=False, indent=2))
    log.info(f"saved → {OUT} ({len(captured)} XHR)")


if __name__ == "__main__":
    main()
