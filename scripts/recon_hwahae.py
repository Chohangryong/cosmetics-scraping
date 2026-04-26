"""화해 사이트 endpoint 정찰. Scrapling DynamicSession capture_xhr 사용.

Usage:
    python scripts/recon_hwahae.py
    -> data/_recon/hwahae.json (endpoint, 카테고리 트리, leaf ranking_id 목록)
"""
import json
import logging
import re
from pathlib import Path

from scrapling.fetchers import DynamicSession

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUT = Path("data/_recon/hwahae.json")
TARGET = "https://www.hwahae.co.kr/rankings"
GATEWAY_RE = r"gateway\.hwahae\.co\.kr/.*"


def _scroll(page):
    for _ in range(5):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(800)
    return page


def _collect_leaves(rc: dict) -> list[dict]:
    """rankingsCategories 트리에서 ranking_detail_id 후보(전체 노드) 수집."""
    leaves = []

    def walk(node, parent_d2=None, parent_d3=None):
        depth = node.get("depth")
        name = node.get("name")
        if depth == 2:
            for c in node.get("children", []):
                walk(c, name, None)
        elif depth == 3:
            if name == "전체":
                leaves.append({
                    "id": node["id"],
                    "depth": 3,
                    "category_path": parent_d2,
                    "category_code": node.get("category_code"),
                })
            else:
                for c in node.get("children", []):
                    walk(c, parent_d2, name)
        elif depth == 4:
            if name == "전체":
                leaves.append({
                    "id": node["id"],
                    "depth": 4,
                    "category_path": f"{parent_d2}>{parent_d3}",
                    "category_code": node.get("category_code"),
                })

    for c in rc.get("children", []):
        walk(c)
    return leaves


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with DynamicSession(capture_xhr=GATEWAY_RE, headless=True) as s:
        page = s.fetch(TARGET, network_idle=True, page_action=_scroll, wait=2000)

    html = page.body if isinstance(page.body, str) else page.body.decode("utf-8", errors="replace")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.S)
    if not m:
        raise SystemExit("__NEXT_DATA__ not found")
    next_data = json.loads(m.group(1))
    pp = next_data["props"]["pageProps"]
    rc = pp.get("rankingsCategories", {})
    leaves = _collect_leaves(rc)

    captured = []
    for x in page.captured_xhr:
        captured.append({"url": x.url, "status": x.status, "method": getattr(x, "method", "GET")})

    sample_endpoint = next((c["url"] for c in captured if "/rankings/" in c["url"] and "/details" in c["url"]), None)

    out = {
        "target": TARGET,
        "captured_xhr": captured,
        "sample_endpoint": sample_endpoint,
        "endpoint_template": "https://gateway.hwahae.co.kr/v14/rankings/{ranking_id}/details?page={page}&page_size={size}",
        "leaf_count": len(leaves),
        "leaves_depth2_count": sum(1 for l in leaves if l["depth"] == 3),
        "leaves_depth3_count": sum(1 for l in leaves if l["depth"] == 4),
        "leaves": leaves,
        "ranking_types": [
            {k: r.get(k) for k in ("id", "ranking_type", "english_name")}
            for r in pp.get("rankings", [])
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    log.info(f"saved {OUT} (leaves={len(leaves)}, captured={len(captured)})")
    if sample_endpoint:
        log.info(f"sample: {sample_endpoint}")


if __name__ == "__main__":
    main()
