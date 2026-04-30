import asyncio
import json
import logging
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

API_TEMPLATE = "https://gateway.hwahae.co.kr/v14/rankings/{ranking_id}/details"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.hwahae.co.kr",
    "Referer": "https://www.hwahae.co.kr/",
}
HWAHAE_CONCURRENCY = 4
HWAHAE_API_DELAY = 0.5
PAGE_SIZE = 20
RECON_PATH = Path("data/_recon/hwahae.json")


def parse_item(item: dict, category: str, page: int, idx_in_page: int) -> dict:
    goods = item.get("goods") or {}
    product = item.get("product") or {}
    brand = item.get("brand") or {}

    rating = product.get("review_rating")
    review_count = product.get("review_count")
    review_score = int(round(rating * 20)) if isinstance(rating, (int, float)) else None

    badge = "NEW" if item.get("is_rank_new") else ""

    return {
        "platform": "hwahae",
        "category": category,
        "product_id": str(goods.get("product_id") or product.get("id") or ""),
        "rank": (page - 1) * PAGE_SIZE + idx_in_page + 1,
        "brand": brand.get("name", ""),
        "name": product.get("name") or goods.get("name", ""),
        "sale_price": (goods.get("discount_price") or None) or (goods.get("price") or None) or (product.get("price") or None),
        "original_price": (goods.get("price") or None) or (product.get("price") or None),
        "discount_rate": goods.get("discount_rate"),
        "badge": badge,
        "review_score": review_score,
        "review_count": review_count,
        "rating": rating,
    }


async def fetch_ranking(
    session: aiohttp.ClientSession,
    ranking_id: int,
    category: str,
    semaphore: asyncio.Semaphore,
    max_rank: int = 50,
) -> list[dict]:
    items: list[dict] = []
    pages = (max_rank + PAGE_SIZE - 1) // PAGE_SIZE
    for page in range(1, pages + 1):
        params = {"page": page, "page_size": PAGE_SIZE}
        async with semaphore:
            try:
                async with session.get(
                    API_TEMPLATE.format(ranking_id=ranking_id),
                    params=params,
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 404:
                        # 소규모 카테고리: page 끝 도달
                        break
                    resp.raise_for_status()
                    data = await resp.json()
            except Exception as e:
                log.error(f"화해 {category}(id={ranking_id}) page={page} 실패: {e}")
                break
            await asyncio.sleep(HWAHAE_API_DELAY)

        details = (data.get("data") or {}).get("details") or []
        if not details:
            break
        for idx, raw in enumerate(details):
            parsed = parse_item(raw, category, page, idx)
            if parsed["rank"] > max_rank:
                return items
            items.append(parsed)
    return items


def load_leaves(scope: str = "b") -> list[tuple[int, str]]:
    """recon 결과에서 (ranking_id, category) 목록 로드.

    scope='a': depth-2 전체만 (13개)
    scope='b': depth-2 + depth-3 전체 (117개)
    """
    if not RECON_PATH.exists():
        raise FileNotFoundError(
            f"{RECON_PATH} 없음. 먼저 'python scripts/recon_hwahae.py' 실행"
        )
    recon = json.loads(RECON_PATH.read_text())
    leaves = recon["leaves"]
    if scope == "a":
        leaves = [l for l in leaves if l["depth"] == 3]

    out = []
    for l in leaves:
        # category slug: "스킨케어>크림" -> "skincare_cream" 형태로 못 만드므로 한글 path 그대로 사용
        out.append((l["id"], l["category_path"]))
    return out


async def fetch_all(
    leaves: list[tuple[int, str]],
    max_rank: int = 50,
) -> list[dict]:
    semaphore = asyncio.Semaphore(HWAHAE_CONCURRENCY)
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_ranking(session, rid, cat, semaphore, max_rank)
            for rid, cat in leaves
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for (rid, cat), result in zip(leaves, results):
        if isinstance(result, Exception):
            log.error(f"화해 {cat}(id={rid}) 수집 실패: {result}")
        else:
            all_items.extend(result)
    return all_items
