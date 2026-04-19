import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

API_URL = "https://api.musinsa.com/api2/hm/web/v5/pans/ranking/sections/231"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.musinsa.com/main/beauty/ranking",
}
MUSINSA_CONCURRENCY = 3
MUSINSA_API_DELAY = 2.0


def parse_item(item: dict, category: str) -> dict:
    info = item.get("info", {})
    ga4 = item.get("onClick", {}).get("eventLog", {}).get("ga4", {}).get("payload", {})
    amp = item.get("onClick", {}).get("eventLog", {}).get("amplitude", {}).get("payload", {})

    flag = ga4.get("item_flag", "")
    badge = "" if flag == "none" else flag

    review_score_raw = amp.get("reviewScore")
    review_count_raw = amp.get("reviewCount")

    return {
        "platform": "musinsa",
        "category": category,
        "product_id": str(item.get("id", "")),
        "rank": item.get("image", {}).get("rank", 0),
        "brand": info.get("brandName", ""),
        "name": info.get("productName", ""),
        "sale_price": info.get("finalPrice"),
        "original_price": ga4.get("original_price"),
        "discount_rate": info.get("discountRatio"),
        "badge": badge,
        "review_score": int(review_score_raw) if review_score_raw is not None else None,
        "review_count": int(review_count_raw) if review_count_raw is not None else None,
        "rating": None,
    }


async def fetch_category(
    session: aiohttp.ClientSession,
    code: str,
    category: str,
    semaphore: asyncio.Semaphore,
    max_rank: int = 50,
) -> list[dict]:
    params = {"storeCode": "beauty", "gf": "A", "categoryCode": code, "page": 1}
    async with semaphore:
        async with session.get(API_URL, params=params, headers=HEADERS) as resp:
            resp.raise_for_status()
            data = await resp.json()
        await asyncio.sleep(MUSINSA_API_DELAY)

    items = []
    for module in data.get("data", {}).get("modules", []):
        for raw_item in module.get("items", []):
            if raw_item.get("type") != "PRODUCT_COLUMN":
                continue
            parsed = parse_item(raw_item, category)
            if parsed["rank"] > max_rank:
                return items
            items.append(parsed)
    return items


async def fetch_all(
    category_codes: list[tuple[str, str]],
    max_rank: int = 50,
) -> list[dict]:
    semaphore = asyncio.Semaphore(MUSINSA_CONCURRENCY)
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_category(session, code, cat, semaphore, max_rank)
            for code, cat in category_codes
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for (code, cat), result in zip(category_codes, results):
        if isinstance(result, Exception):
            log.error(f"무신사 {cat}({code}) 수집 실패: {result}")
        else:
            all_items.extend(result)
    return all_items
