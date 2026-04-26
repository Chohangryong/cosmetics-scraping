"""교차 플랫폼 분석 리포트 (B2B 샘플).

매칭쌍 기반:
  ① 동일상품 채널별 순위 갭
  ② 별점(OY) vs 리뷰점수(MS) 괴리
  ③ 가격/할인 차이
  ④ OY 상위인데 무신사 미진입 브랜드/상품 (영업 리스트)
"""
import sys
from collections import defaultdict
from difflib import SequenceMatcher

from sqlalchemy import text

from scripts.match_poc import normalize
from src.models import get_engine, get_session

SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260426_193046"
THRESHOLD = 0.70


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_price(p):
    return f"{int(p):,}" if p else "-"


def main():
    engine = get_engine("data/beauty_ranking.db")
    db = get_session(engine)

    rows = db.execute(text("""
        SELECT p.brand
        FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
        WHERE rs.session_id=:sid
        GROUP BY p.brand HAVING COUNT(DISTINCT rs.platform)=2
    """), {"sid": SESSION}).fetchall()
    common_brands = [r[0] for r in rows]

    rows = db.execute(text("""
        SELECT rs.platform, p.brand, p.product_name, rs.rank, rs.category,
               rs.sale_price, rs.original_price, rs.discount_rate,
               rs.rating, rs.review_count, rs.review_score
        FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
        WHERE rs.session_id=:sid
    """), {"sid": SESSION}).fetchall()

    by_brand_plat: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        m = dict(r._mapping)
        m["norm"] = normalize(m["product_name"])
        by_brand_plat[(m["brand"], m["platform"])].append(m)

    # 매칭 (브랜드 내 best match)
    pairs = []
    for brand in common_brands:
        oy_items = by_brand_plat.get((brand, "oliveyoung"), [])
        ms_items = by_brand_plat.get((brand, "musinsa"), [])
        used_ms = set()
        # OY 상위 순부터 매칭 (인기 상품 우선)
        for o in sorted(oy_items, key=lambda x: x["rank"]):
            best, best_s = None, 0.0
            for i, m in enumerate(ms_items):
                if i in used_ms:
                    continue
                s = sim(o["norm"], m["norm"])
                if s > best_s:
                    best_s, best = s, (i, m)
            if best and best_s >= THRESHOLD:
                used_ms.add(best[0])
                pairs.append((best_s, o, best[1]))

    print(f"\n매칭쌍: {len(pairs)}개 (threshold={THRESHOLD}, session={SESSION})")
    print("=" * 90)

    # ① 순위 갭 ─────────────────────────────────────────
    print("\n① 동일상품 채널별 순위 갭 TOP 15  (|OY-MS| 큰 순)")
    print("-" * 90)
    print(f"  {'브랜드':<10} {'상품(OY)':<35} {'OY':>4} {'MS':>4} {'GAP':>5} {'강세':>4}")
    gaps = sorted(pairs, key=lambda x: -abs(x[1]["rank"] - x[2]["rank"]))
    for s, o, m in gaps[:15]:
        gap = o["rank"] - m["rank"]
        winner = "OY" if gap < 0 else ("MS" if gap > 0 else "=")
        print(f"  {trunc(o['brand'],10):<10} {trunc(o['product_name'],35):<35} "
              f"{o['rank']:>4} {m['rank']:>4} {gap:>+5} {winner:>4}")

    # ② 별점 vs 리뷰점수 괴리 ────────────────────────────
    print("\n② 별점(OY ★0~5) vs 리뷰점수(MS 0~100) 정렬 (정규화)")
    print("-" * 90)
    print(f"  {'브랜드':<10} {'상품':<35} {'OY★':>5} {'OY정규화':>9} {'MS점수':>7} {'차':>5}")
    div = []
    for s, o, m in pairs:
        if o["rating"] is None or m["review_score"] is None:
            continue
        oy_n = float(o["rating"]) * 20  # 0~100
        ms_score = float(m["review_score"])
        diff = oy_n - ms_score
        div.append((diff, o, m, oy_n, ms_score))
    div.sort(key=lambda x: -abs(x[0]))
    for diff, o, m, oy_n, ms_s in div[:10]:
        print(f"  {trunc(o['brand'],10):<10} {trunc(o['product_name'],35):<35} "
              f"{o['rating']:>5} {oy_n:>8.1f} {ms_s:>7.1f} {diff:>+5.1f}")
    if not div:
        print("  (MS rating 데이터 없음 — 스키마 확인 필요)")

    # ③ 가격/할인 차이 ─────────────────────────────────
    print("\n③ 가격 차이 TOP 10  (OY-MS 절대값 큰 순)")
    print("-" * 90)
    print(f"  {'브랜드':<10} {'상품':<35} {'OY가':>9} {'MS가':>9} {'차':>9} {'OY%':>4} {'MS%':>4}")
    pdiff = [(abs((o["sale_price"] or 0) - (m["sale_price"] or 0)), s, o, m)
             for s, o, m in pairs if o["sale_price"] and m["sale_price"]]
    pdiff.sort(key=lambda x: -x[0])
    for d, s, o, m in pdiff[:10]:
        delta = (o["sale_price"] or 0) - (m["sale_price"] or 0)
        print(f"  {trunc(o['brand'],10):<10} {trunc(o['product_name'],35):<35} "
              f"{fmt_price(o['sale_price']):>9} {fmt_price(m['sale_price']):>9} "
              f"{delta:>+9,} {(o['discount_rate'] or 0):>3}% {(m['discount_rate'] or 0):>3}%")

    # ④ OY 상위인데 무신사 미진입 ─────────────────────
    print("\n④ OY TOP10인데 무신사 매칭 실패 = 무신사 입점 후보 (인디 영업 리스트)")
    print("-" * 90)
    matched_oy_ids = {id(o) for _, o, _ in pairs}
    candidates = []
    for brand in common_brands:
        for o in by_brand_plat.get((brand, "oliveyoung"), []):
            if id(o) not in matched_oy_ids and o["rank"] <= 10:
                candidates.append(o)
    # 비공통 브랜드도 추가 (무신사에 브랜드 자체가 없음)
    ms_brands = {b for (b, p) in by_brand_plat if p == "musinsa"}
    for (brand, plat), items in by_brand_plat.items():
        if plat != "oliveyoung" or brand in ms_brands:
            continue
        for o in items:
            if o["rank"] <= 5:
                candidates.append(o)
    candidates.sort(key=lambda x: x["rank"])
    print(f"  {'카테고리':<14} {'OY순위':>6} {'브랜드':<12} {'상품':<40} {'리뷰수':>7}")
    for o in candidates[:20]:
        print(f"  {o['category']:<14} {o['rank']:>6} {trunc(o['brand'],12):<12} "
              f"{trunc(o['product_name'],40):<40} {(o['review_count'] or 0):>7,}")

    print()
    print("=" * 90)


if __name__ == "__main__":
    main()
