"""미매칭 OY/MS 브랜드를 화해 search SSR로 lookup하여 화해 존재 여부와 제품 수 확인."""
import asyncio
import json
import re
import sys
from urllib.parse import quote

import aiohttp

CANDIDATES = [
    # (브랜드명, 출처)
    ("라운드어라운드", "OY"),
    ("바노바기", "MS"),
    ("슬로우허밍", "OY"),
    ("르멘트", "OY+MS"),
    ("디어스킨", "OY"),
    ("유기농본", "OY"),
    ("동아제약", "OY"),
    ("라우쉬", "OY+MS"),
    ("케라스타즈", "OY"),
    ("코링코", "OY+MS"),
    ("더툴랩", "OY+MS"),
    ("제이엠더블유", "MS"),
    ("어덴비", "MS"),
    ("글로스앤글로우", "MS"),
    ("닥터유", "MS"),
    ("라피타", "MS"),
    ("모에브", "MS"),
    ("스나이델뷰티", "MS"),
    ("베이지크", "MS"),
    ("바노바기", "MS"),  # dup ok
]

URL = "https://www.hwahae.co.kr/search?q={}"
NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', re.S)


async def lookup(session: aiohttp.ClientSession, brand: str) -> dict:
    url = URL.format(quote(brand))
    try:
        async with session.get(url, timeout=15) as r:
            html = await r.text()
        m = NEXT_RE.search(html)
        if not m:
            return {"brand": brand, "ok": False, "err": "no __NEXT_DATA__"}
        data = json.loads(m.group(1))
        prods = data.get("props", {}).get("pageProps", {}).get("products", {})
        meta = prods.get("meta", {})
        total = meta.get("totalResultCount", 0)
        items = prods.get("products", [])
        # brand 표기 분포
        brand_disp = {}
        for p in items:
            b = p.get("brand", "")
            brand_disp[b] = brand_disp.get(b, 0) + 1
        # 가장 흔한 brand 표기
        top_brand = max(brand_disp, key=brand_disp.get) if brand_disp else None
        # 첫 제품 샘플
        sample = items[0] if items else {}
        return {
            "brand": brand,
            "ok": True,
            "total": total,
            "top_brand_label": top_brand,
            "sample_product": sample.get("productName"),
            "sample_rating": sample.get("avgRatings"),
            "sample_reviews": sample.get("reviewCount"),
        }
    except Exception as e:
        return {"brand": brand, "ok": False, "err": str(e)}


async def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko",
    }
    sem = asyncio.Semaphore(4)
    async with aiohttp.ClientSession(headers=headers) as session:
        async def bound(b, src):
            async with sem:
                r = await lookup(session, b)
                r["source"] = src
                return r
        tasks = [bound(b, src) for b, src in CANDIDATES]
        results = await asyncio.gather(*tasks)

    print(f"{'브랜드':12s} | {'출처':6s} | {'화해':6s} | {'표기':30s} | 샘플 제품")
    print("-" * 100)
    for r in results:
        if not r["ok"]:
            print(f"{r['brand']:12s} | {r['source']:6s} | ERR    | {r.get('err','')}")
            continue
        total = r["total"]
        flag = f"{total:>4d}건" if total else "  없음"
        label = (r["top_brand_label"] or "-")[:30]
        sample = (r["sample_product"] or "-")[:30]
        rating = r["sample_rating"] or 0
        rev = r["sample_reviews"] or 0
        print(f"{r['brand']:12s} | {r['source']:6s} | {flag} | {label:30s} | {sample} (★{rating} R{rev})")


if __name__ == "__main__":
    asyncio.run(main())
