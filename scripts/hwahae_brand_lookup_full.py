"""미매칭 OY/MS 브랜드 219건 전수 화해 search lookup.

정확매칭 필터: search 결과 제품의 brand label에서 한글 부분이 검색어와 정확히 일치할 때만 매칭으로 카운트.
출력: data/_recon/hwahae_brand_lookup.json + 콘솔 요약.
"""
import asyncio
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

import aiohttp

SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260430_231616"
OUT = Path("data/_recon/hwahae_brand_lookup.json")
URL = "https://www.hwahae.co.kr/search?q={}"
NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', re.S)
NORM_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko",
}


def normalize(s: str) -> str:
    return NORM_RE.sub("", (s or "")).lower()


def get_unmatched_brands(db_path: str, session: str) -> list[tuple[str, str]]:
    """현 매칭 스크립트 로직 재사용: alias 적용 + fuzzy 후 미매칭만 추출."""
    from difflib import SequenceMatcher
    BRAND_ALIAS = {
        "캘빈클라인": "CK", "캘빈클라인 퍼퓸": "CK", "쓰리씨이": "3CE",
        "에이에이치씨": "AHC", "GNM자연의품격": "GNM", "랑방 퍼퓸": "랑방",
        "몽블랑 퍼퓸": "몽블랑", "헤트라스 뷰티": "헤트라스", "베르사체 퍼퓸": "베르사체",
        "메종 마르지엘라 퍼퓸": "메종 마르지엘라", "에르메스 어메니티": "에르메스",
        "정샘물": "정샘물뷰티", "로레알": "로레알파리",
        "로레알 프로페셔널": "로레알프로페셔널파리", "CKD": "CKDGUARANTEED",
    }

    def norm(name: str) -> str:
        canonical = BRAND_ALIAS.get(name.strip(), name)
        return NORM_RE.sub("", canonical.strip().lower())

    con = sqlite3.connect(db_path)
    rows = con.execute(
        """SELECT p.platform, p.brand FROM ranking_snapshots rs
           JOIN products p ON rs.product_id=p.id
           WHERE rs.session_id=? AND p.brand IS NOT NULL AND p.brand!=''
           GROUP BY p.platform, p.brand""",
        (session,),
    ).fetchall()

    by_plat: dict[str, dict[str, str]] = {"hwahae": {}, "oliveyoung": {}, "musinsa": {}}
    for plat, brand in rows:
        n = norm(brand)
        if n:
            by_plat[plat].setdefault(n, brand)

    hw_keys = list(by_plat["hwahae"].keys())

    def matched_to_hw(plat: str) -> set[str]:
        keys = set(by_plat[plat]) & set(hw_keys)
        for k in set(by_plat[plat]) - keys:
            for hwk in hw_keys:
                if SequenceMatcher(None, k, hwk).ratio() >= 0.85:
                    keys.add(k)
                    break
        return keys

    oy_matched = matched_to_hw("oliveyoung")
    ms_matched = matched_to_hw("musinsa")

    unmatched = []
    for n, disp in by_plat["oliveyoung"].items():
        if n not in oy_matched:
            unmatched.append((disp, "OY"))
    for n, disp in by_plat["musinsa"].items():
        if n not in ms_matched:
            # 양 채널 모두 미매칭이면 OY+MS 표기
            existing = next((u for u in unmatched if u[0] == disp), None)
            if existing:
                unmatched.remove(existing)
                unmatched.append((disp, "OY+MS"))
            else:
                unmatched.append((disp, "MS"))
    return unmatched


async def lookup(session: aiohttp.ClientSession, brand: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        try:
            async with session.get(URL.format(quote(brand)), timeout=15) as r:
                html = await r.text()
        except Exception as e:
            return {"brand": brand, "ok": False, "err": str(e)}

    m = NEXT_RE.search(html)
    if not m:
        return {"brand": brand, "ok": False, "err": "no __NEXT_DATA__"}
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        return {"brand": brand, "ok": False, "err": f"json: {e}"}

    prods = data.get("props", {}).get("pageProps", {}).get("products", {})
    items = prods.get("products", [])
    total = prods.get("meta", {}).get("totalResultCount", 0)

    # 정확매칭: brand label에서 한글 부분 추출 → normalize 비교
    target_norm = normalize(brand)
    exact_matches = 0
    label_counts: dict[str, int] = {}
    sample_exact = None
    for p in items:
        lbl = p.get("brand", "")
        # "코링코 (CORINGCO)" 형태에서 한글 부분만
        kor = re.sub(r"\([^)]*\)", "", lbl).strip()
        kn = normalize(kor)
        label_counts[lbl] = label_counts.get(lbl, 0) + 1
        if kn == target_norm:
            exact_matches += 1
            if sample_exact is None:
                sample_exact = {
                    "brand_label": lbl,
                    "product_name": p.get("productName"),
                    "rating": p.get("avgRatings"),
                    "reviews": p.get("reviewCount"),
                }
    top_label = max(label_counts, key=label_counts.get) if label_counts else None
    top_label_kor = re.sub(r"\([^)]*\)", "", top_label or "").strip()
    is_exact_top = normalize(top_label_kor) == target_norm

    return {
        "brand": brand,
        "ok": True,
        "total": total,
        "page_size_n": len(items),
        "exact_in_page": exact_matches,
        "top_label": top_label,
        "top_label_is_exact": is_exact_top,
        "sample_exact": sample_exact,
    }


def classify(r: dict) -> str:
    if not r.get("ok"):
        return "ERROR"
    if r["total"] == 0:
        return "MISSING"  # 화해에 없음
    if r["top_label_is_exact"] and r["exact_in_page"] >= 3:
        return "STRONG"  # 명확히 화해 보유
    if r["exact_in_page"] >= 1:
        return "PARTIAL"  # 일부 매칭 (브랜드 분기 또는 부분일치)
    return "NOISE"  # 검색 결과는 있으나 다른 브랜드 (오매칭)


async def main():
    candidates = get_unmatched_brands("data/beauty_ranking.db", SESSION)
    # 명백한 화해 미수집 카테고리 키워드 1차 필터(스킵 표시)
    SKIP_PAT = re.compile(r"질레트|쉬크|텐가|사가미|좋은느낌|쏘피|화이트|위스퍼|하기스|디어스킨"
                          r"|오호라|데싱디바|글램팜|탱글티저|보다나|다이슨|필립스|라파엘|글로벌마켓"
                          r"|핑거수트|로지킴|닥터유")
    print(f"미매칭 후보: {len(candidates)}건 (전수 lookup, concurrency=4)")

    sem = asyncio.Semaphore(4)
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        results = await asyncio.gather(*[lookup(s, b, sem) for b, _ in candidates])

    # source 매핑
    src_map = {b: src for b, src in candidates}
    for r in results:
        r["source"] = src_map.get(r["brand"], "?")
        r["verdict"] = classify(r)

    # 결과 저장
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # 요약
    buckets: dict[str, list[dict]] = {"STRONG": [], "PARTIAL": [], "NOISE": [], "MISSING": [], "ERROR": []}
    for r in results:
        buckets[r["verdict"]].append(r)

    print()
    print(f"=== 분류 결과 (n={len(results)}) ===")
    for v in ("STRONG", "PARTIAL", "NOISE", "MISSING", "ERROR"):
        print(f"  {v:8s}: {len(buckets[v]):3d}건")
    print()
    print(f"=== STRONG (화해 신규 매칭 회수 후보) {len(buckets['STRONG'])}건 ===")
    for r in sorted(buckets["STRONG"], key=lambda x: -x["total"]):
        print(f"  {r['brand']:14s} | {r['source']:6s} | total={r['total']:>5} | {r['top_label']}")
    print()
    print(f"=== PARTIAL (검토 필요) {len(buckets['PARTIAL'])}건 ===")
    for r in sorted(buckets["PARTIAL"], key=lambda x: -x["exact_in_page"]):
        print(f"  {r['brand']:14s} | {r['source']:6s} | exact={r['exact_in_page']}/{r['page_size_n']} | top={r['top_label']}")
    print()
    print(f"=== NOISE (다른 브랜드 1위, 화해 미존재 의심) {len(buckets['NOISE'])}건 ===")
    for r in sorted(buckets["NOISE"], key=lambda x: -x["total"])[:30]:
        print(f"  {r['brand']:14s} | {r['source']:6s} | total={r['total']:>5} | top={r['top_label']}")
    if len(buckets["NOISE"]) > 30:
        print(f"  ... +{len(buckets['NOISE']) - 30}건 (json에 전체)")
    print()
    print(f"=== MISSING (검색결과 0) {len(buckets['MISSING'])}건 ===")
    for r in buckets["MISSING"][:30]:
        print(f"  {r['brand']:14s} | {r['source']}")
    if len(buckets["MISSING"]) > 30:
        print(f"  ... +{len(buckets['MISSING']) - 30}건")


if __name__ == "__main__":
    asyncio.run(main())
