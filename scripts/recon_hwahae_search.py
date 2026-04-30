"""화해 search XHR 정찰. 브랜드명으로 검색 시 호출되는 gateway endpoint 캡처."""
import json
import logging
import re
from pathlib import Path

from scrapling.fetchers import DynamicSession

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUT = Path("data/_recon/hwahae_search.json")
TARGET = "https://www.hwahae.co.kr/search?q=%EB%9D%BC%EC%9A%B4%EB%93%9C%EC%96%B4%EB%9D%BC%EC%9A%B4%EB%93%9C"
GATEWAY_RE = r"gateway\.hwahae\.co\.kr/.*"


def _scroll(page):
    for _ in range(3):
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(800)
    return page


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with DynamicSession(capture_xhr=GATEWAY_RE, headless=True) as s:
        page = s.fetch(TARGET, network_idle=True, page_action=_scroll, wait=2000)

    captured = []
    for x in page.captured_xhr:
        item = {"url": x.url, "status": x.status, "method": getattr(x, "method", "GET")}
        body = getattr(x, "response_body", None) or getattr(x, "body", None)
        if body:
            try:
                item["body_preview"] = body[:500] if isinstance(body, str) else body[:500].decode("utf-8", errors="replace")
            except Exception:
                pass
        req_headers = getattr(x, "request_headers", None)
        if req_headers:
            item["request_headers"] = {k: v for k, v in dict(req_headers).items() if k.lower() in ("authorization", "hwahae-device-id", "hwahae-user-id")}
        captured.append(item)

    OUT.write_text(json.dumps({"target": TARGET, "captured_xhr": captured}, ensure_ascii=False, indent=2))
    print(f"captured {len(captured)} XHRs -> {OUT}")
    for c in captured:
        print(f"  [{c.get('status')}] {c.get('method')} {c['url']}")


if __name__ == "__main__":
    main()
