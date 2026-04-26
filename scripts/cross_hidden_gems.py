"""양 플랫폼 공통 숨은 강자.

매칭쌍 중 OY rating ≥ 4.8 AND MS review_score ≥ 95 인데
한쪽 또는 양쪽에서 순위 ≥ 30 → 양 채널 만족도 높은데 노출 부족.
"""
import sys
from collections import defaultdict
from difflib import SequenceMatcher

from sqlalchemy import text

from scripts.match_poc import normalize
from src.models import get_engine, get_session

SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260426_193046"
THRESHOLD = 0.70


def sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


def trunc(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    db = get_session(get_engine("data/beauty_ranking.db"))
    rows = db.execute(text("""
        SELECT p.brand FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
        WHERE rs.session_id=:sid GROUP BY p.brand HAVING COUNT(DISTINCT rs.platform)=2
    """), {"sid": SESSION}).fetchall()
    common_brands = [r[0] for r in rows]

    rows = db.execute(text("""
        SELECT rs.platform, p.brand, p.product_name, rs.rank, rs.category,
               rs.rating, rs.review_count, rs.review_score
        FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
        WHERE rs.session_id=:sid
    """), {"sid": SESSION}).fetchall()

    by = defaultdict(list)
    for r in rows:
        m = dict(r._mapping)
        m["norm"] = normalize(m["product_name"])
        by[(m["brand"], m["platform"])].append(m)

    # 매칭
    pairs = []
    for brand in common_brands:
        oy_items = by.get((brand, "oliveyoung"), [])
        ms_items = by.get((brand, "musinsa"), [])
        used = set()
        for o in sorted(oy_items, key=lambda x: x["rank"]):
            best, best_s = None, 0.0
            for i, m in enumerate(ms_items):
                if i in used:
                    continue
                s = sim(o["norm"], m["norm"])
                if s > best_s:
                    best_s, best = s, (i, m)
            if best and best_s >= THRESHOLD:
                used.add(best[0])
                pairs.append((best_s, o, best[1]))

    # 분류
    both_high = []  # 양쪽 만족도 높음
    for s, o, m in pairs:
        if (o["rating"] is not None and o["rating"] >= 4.8 and
            m["review_score"] is not None and m["review_score"] >= 95):
            both_high.append((s, o, m))

    print(f"\n매칭쌍 {len(pairs)}개 중 양 채널 만족도 높음(OY★≥4.8, MS≥95): {len(both_high)}개")
    print("=" * 95)

    # ① 양쪽 다 30위 밖 = 진짜 숨은 강자
    deep = [(s, o, m) for s, o, m in both_high if o["rank"] >= 30 and m["rank"] >= 30]
    deep.sort(key=lambda x: x[1]["rank"] + x[2]["rank"])
    print(f"\n① 양쪽 모두 30위+ (진짜 숨은 강자, {len(deep)}개)")
    print("-" * 95)
    print(f"  {'브랜드':<10} {'카테고리(OY/MS)':<18} {'OY순위':>5} {'★':>4} {'리뷰':>7} {'MS순위':>5} {'점수':>4} {'리뷰':>6}")
    for s, o, m in deep:
        print(f"  {trunc(o['brand'],10):<10} {trunc(o['category'][:8]+'/'+m['category'][:8],18):<18} "
              f"{o['rank']:>5} {o['rating']:>4} {(o['review_count'] or 0):>7,} "
              f"{m['rank']:>5} {m['review_score']:>4} {(m['review_count'] or 0):>6,}")

    # ② OY 강세 / MS 숨음 (OY ≤ 15 & MS ≥ 30)
    oy_strong = [(s, o, m) for s, o, m in both_high if o["rank"] <= 15 and m["rank"] >= 30]
    oy_strong.sort(key=lambda x: -(x[2]["rank"] - x[1]["rank"]))
    print(f"\n② OY 상위(≤15) + MS 숨음(≥30) → 무신사 노출 강화 후보 ({len(oy_strong)}개)")
    print("-" * 95)
    for s, o, m in oy_strong[:15]:
        print(f"  {trunc(o['brand'],10):<10} OY#{o['rank']:>2}/MS#{m['rank']:>2}  ★{o['rating']} "
              f"{(o['review_count'] or 0):>6,}리뷰 | MS{m['review_score']}점 → "
              f"{trunc(o['product_name'],45)}")

    # ③ MS 강세 / OY 숨음 (MS ≤ 15 & OY ≥ 30)
    ms_strong = [(s, o, m) for s, o, m in both_high if m["rank"] <= 15 and o["rank"] >= 30]
    ms_strong.sort(key=lambda x: -(x[1]["rank"] - x[2]["rank"]))
    print(f"\n③ MS 상위(≤15) + OY 숨음(≥30) → 올영 노출 강화 후보 ({len(ms_strong)}개)")
    print("-" * 95)
    for s, o, m in ms_strong[:15]:
        print(f"  {trunc(o['brand'],10):<10} MS#{m['rank']:>2}/OY#{o['rank']:>2}  ★{o['rating']} "
              f"{(o['review_count'] or 0):>6,}리뷰 | MS{m['review_score']}점 → "
              f"{trunc(o['product_name'],45)}")

    # ④ 양채널 모두 TOP10 (메가 셀러)
    mega = [(s, o, m) for s, o, m in both_high if o["rank"] <= 10 and m["rank"] <= 10]
    mega.sort(key=lambda x: x[1]["rank"] + x[2]["rank"])
    print(f"\n④ 양채널 모두 TOP10 = 메가 셀러 ({len(mega)}개)")
    print("-" * 95)
    for s, o, m in mega:
        print(f"  {trunc(o['brand'],10):<10} OY#{o['rank']}/MS#{m['rank']}  ★{o['rating']} "
              f"{(o['review_count'] or 0):>6,}리뷰 | MS{m['review_score']}점 → "
              f"{trunc(o['product_name'],50)}")

    print()


if __name__ == "__main__":
    main()
