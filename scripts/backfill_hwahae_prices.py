"""화해 가격 백필 — 비커머스(goods=null) 제품의 product.price를 사용해
ranking_snapshots의 NULL 가격을 채운다.

대상 세션: 인자로 받음 (default 20260430_231616)
"""
import asyncio
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import aiohttp

DB = Path(__file__).resolve().parents[1] / "data/beauty_ranking.db"
RECON = Path(__file__).resolve().parents[1] / "data/_recon/hwahae.json"
SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260430_231616"

API = "https://gateway.hwahae.co.kr/v14/rankings/{rid}/details"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://www.hwahae.co.kr",
    "Referer": "https://www.hwahae.co.kr/",
}
PAGE_SIZE = 20
CONCURRENCY = 4


def load_targets() -> dict[str, list[tuple[str, int]]]:
    """category -> [(channel_pid, rank), ...] (NULL 가격만)."""
    con = sqlite3.connect(DB)
    rows = con.execute(
        """
        SELECT rs.category, p.product_id, rs.rank
        FROM ranking_snapshots rs
        JOIN products p ON p.id = rs.product_id
        WHERE rs.session_id = ?
          AND rs.platform = 'hwahae'
          AND rs.sale_price IS NULL
        """,
        (SESSION,),
    ).fetchall()
    con.close()
    out: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for cat, pid, rank in rows:
        out[cat].append((pid, rank))
    return out


def load_cat_to_rid() -> dict[str, int]:
    recon = json.loads(RECON.read_text())
    return {l["category_path"]: l["id"] for l in recon["leaves"]}


async def fetch_page(s: aiohttp.ClientSession, rid: int, page: int, sem: asyncio.Semaphore):
    async with sem:
        async with s.get(
            API.format(rid=rid),
            params={"page": page, "page_size": PAGE_SIZE},
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status != 200:
                return []
            d = await r.json()
            return (d.get("data") or {}).get("details") or []


async def main():
    targets = load_targets()
    cat2rid = load_cat_to_rid()
    print(f"백필 대상: {sum(len(v) for v in targets.values())}건 / {len(targets)} 카테고리")

    # 카테고리당 필요한 page 집합 계산
    plan: list[tuple[str, int, int]] = []  # (cat, rid, page)
    for cat, items in targets.items():
        rid = cat2rid.get(cat)
        if not rid:
            print(f"  ⚠ ranking_id 없음: {cat}")
            continue
        pages = sorted({(rk - 1) // PAGE_SIZE + 1 for _, rk in items})
        for pg in pages:
            plan.append((cat, rid, pg))
    print(f"호출 예정: {len(plan)} 페이지")

    sem = asyncio.Semaphore(CONCURRENCY)
    # pid -> price (해당 카테고리에서 본 product.price)
    pid_price: dict[str, int] = {}

    async with aiohttp.ClientSession() as s:
        async def run(cat, rid, page):
            details = await fetch_page(s, rid, page, sem)
            await asyncio.sleep(0.3)
            return cat, details

        results = await asyncio.gather(*[run(c, r, p) for c, r, p in plan])

    for cat, details in results:
        for it in details:
            p = it.get("product") or {}
            g = it.get("goods") or {}
            pid = str(p.get("id") or "")
            if not pid:
                continue
            price = g.get("discount_price") or g.get("price") or p.get("price")
            if price is not None and pid not in pid_price:
                pid_price[pid] = price

    # UPDATE
    con = sqlite3.connect(DB)
    cur = con.cursor()
    updated = 0
    missing_after = 0
    for cat, items in targets.items():
        for pid, _rank in items:
            price = pid_price.get(pid)
            if price is None:
                missing_after += 1
                continue
            cur.execute(
                """
                UPDATE ranking_snapshots
                SET sale_price = COALESCE(sale_price, ?),
                    original_price = COALESCE(original_price, ?)
                WHERE session_id = ?
                  AND platform = 'hwahae'
                  AND product_id = (SELECT id FROM products WHERE platform='hwahae' AND product_id=?)
                  AND category = ?
                  AND sale_price IS NULL
                """,
                (price, price, SESSION, pid, cat),
            )
            updated += cur.rowcount
    con.commit()
    con.close()
    print(f"UPDATE 완료: {updated} rows | 가격 못찾음: {missing_after}")


if __name__ == "__main__":
    asyncio.run(main())
