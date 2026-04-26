"""교차 플랫폼 상품 매칭 PoC.

102개 공통 브랜드 안에서 OY ↔ 무신사 상품을 fuzzy match.
매칭률과 샘플을 출력. 영구 모듈 아님 — 가치 검증용.
"""
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

from sqlalchemy import text

from src.models import get_engine, get_session

SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260426_193046"
THRESHOLD = 0.62  # similarity 컷

# 정규화용 패턴
BRACKETS = re.compile(r"[\[【\(].*?[\]】\)]")  # [], 【】, ()
EXTRA = re.compile(r"\s+")
NOISE_TOKENS = {
    "기획", "단독", "증정", "한정", "리필", "미니", "더블", "세트", "택1", "택일",
    "신상", "어워즈", "수상", "대용량", "특가", "할인", "오리지널",
}
UNIT_PAT = re.compile(r"\d+\s*(ml|g|kg|매|개|종|호|호기|매입|봉)\b", re.I)


def normalize(name: str) -> str:
    s = BRACKETS.sub(" ", name)
    s = re.sub(r"[+\-/·,~_!?\"']", " ", s)
    tokens = [t for t in s.split() if t and t not in NOISE_TOKENS]
    s = " ".join(tokens).lower()
    s = EXTRA.sub(" ", s).strip()
    return s


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def main():
    engine = get_engine("data/beauty_ranking.db")
    db = get_session(engine)

    # 양 플랫폼 진입 브랜드
    rows = db.execute(text("""
        SELECT p.brand
        FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
        WHERE rs.session_id=:sid
        GROUP BY p.brand HAVING COUNT(DISTINCT rs.platform)=2
    """), {"sid": SESSION}).fetchall()
    common_brands = [r[0] for r in rows]
    print(f"공통 브랜드: {len(common_brands)}개")

    # 브랜드별 상품 로드
    products = db.execute(text("""
        SELECT rs.platform, p.brand, p.product_name, rs.rank, rs.category,
               rs.sale_price, rs.rating, rs.review_count
        FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
        WHERE rs.session_id=:sid AND p.brand IN ({})
    """.format(",".join(f"'{b}'" for b in common_brands))),
        {"sid": SESSION},
    ).fetchall()

    by_brand_plat: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in products:
        m = dict(r._mapping)
        m["norm"] = normalize(m["product_name"])
        by_brand_plat[(m["brand"], m["platform"])].append(m)

    # 매칭
    matches = []
    oy_total = 0
    matched_oy = 0
    for brand in common_brands:
        oy_items = by_brand_plat.get((brand, "oliveyoung"), [])
        ms_items = by_brand_plat.get((brand, "musinsa"), [])
        oy_total += len(oy_items)
        for o in oy_items:
            best = None
            best_score = 0.0
            for m in ms_items:
                s = sim(o["norm"], m["norm"])
                if s > best_score:
                    best_score = s
                    best = m
            if best and best_score >= THRESHOLD:
                matched_oy += 1
                matches.append((best_score, o, best))

    print(f"OY 상품(공통브랜드): {oy_total}")
    print(f"매칭됨(threshold={THRESHOLD}): {matched_oy} ({matched_oy/oy_total*100:.1f}%)")
    print()

    # 매칭 분포
    buckets = defaultdict(int)
    for s, _, _ in matches:
        b = round(s, 1)
        buckets[b] += 1
    print("=== 유사도 분포 ===")
    for b in sorted(buckets):
        print(f"  {b:.1f}: {'#' * buckets[b]} ({buckets[b]})")
    print()

    # 샘플: 높은 점수
    print("=== 매칭 샘플 (sim 높은 순 TOP 15) ===")
    matches.sort(key=lambda x: -x[0])
    for s, o, m in matches[:15]:
        print(f"[{s:.2f}] {o['brand']:<10} | OY#{o['rank']:>2} {o['product_name'][:40]}")
        print(f"          {' '*10} | MS#{m['rank']:>2} {m['product_name'][:40]}")

    # 샘플: 임계값 근처 (false positive 위험 평가)
    print()
    print("=== 임계값 근처 (0.62~0.68) ===")
    near = [m for m in matches if 0.62 <= m[0] < 0.68]
    for s, o, m in near[:10]:
        print(f"[{s:.2f}] {o['brand']:<10} | OY {o['product_name'][:40]}")
        print(f"          {' '*10} | MS {m['product_name'][:40]}")

    # 매칭 안 된 OY 상품 (공통 브랜드 안에서)
    print()
    print(f"=== 매칭 실패한 OY 상품 샘플 (총 {oy_total - matched_oy}건) ===")
    matched_ids = {id(o) for _, o, _ in matches}
    misses = []
    for brand in common_brands:
        for o in by_brand_plat.get((brand, "oliveyoung"), []):
            if id(o) not in matched_ids:
                misses.append(o)
    for o in misses[:10]:
        print(f"  {o['brand']:<10} | {o['product_name'][:60]}")


if __name__ == "__main__":
    main()
