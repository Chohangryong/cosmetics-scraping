"""P1: 매칭된 브랜드 풀 안에서 OY/MS/HW 제품명 fuzzy 매칭 → product_matches 적재.

알고리즘:
1. brand_aliases.canonical_brand 기준으로 채널 묶음
2. 채널 페어(OY-MS, OY-HW, MS-HW) 각각 best fuzzy 매칭
3. greedy 1-to-1 (한 제품은 다른 채널 1개에만 매칭)
4. 3-way 그래프 walk: OY-MS와 OY-HW 둘 다 같은 OY를 거쳐 연결되면 3-way
"""
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher

DB = "data/beauty_ranking.db"
SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260430_231616"
THRESHOLD = 0.70  # 메모 학습: 0.70이 실용

BRACKETS = re.compile(r"[\[【\(].*?[\]】\)]")
EXTRA = re.compile(r"\s+")
UNIT_PAT = re.compile(r"\d+\s*(ml|g|kg|매|개|종|호|호기|매입|봉)\b", re.I)
NOISE_TOKENS = {
    "기획", "단독", "증정", "한정", "리필", "미니", "더블", "세트", "택1", "택일",
    "신상", "어워즈", "수상", "대용량", "특가", "할인", "오리지널", "리뉴얼",
    "공식", "정품", "공구", "대용량팩", "패키지",
}


def normalize(name: str) -> str:
    s = BRACKETS.sub(" ", name)
    s = UNIT_PAT.sub(" ", s)
    s = re.sub(r"[+\-/·,~_!?\"']", " ", s)
    tokens = [t for t in s.split() if t and t not in NOISE_TOKENS]
    return EXTRA.sub(" ", " ".join(tokens)).strip().lower()


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 테이블 생성
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS product_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_brand TEXT NOT NULL,
        oy_product_id INTEGER,
        ms_product_id INTEGER,
        hw_product_id INTEGER,
        match_score REAL NOT NULL,
        match_method TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(oy_product_id) REFERENCES products(id),
        FOREIGN KEY(ms_product_id) REFERENCES products(id),
        FOREIGN KEY(hw_product_id) REFERENCES products(id)
    );
    CREATE INDEX IF NOT EXISTS idx_pm_brand ON product_matches(canonical_brand);
    CREATE INDEX IF NOT EXISTS idx_pm_oy ON product_matches(oy_product_id);
    CREATE INDEX IF NOT EXISTS idx_pm_ms ON product_matches(ms_product_id);
    CREATE INDEX IF NOT EXISTS idx_pm_hw ON product_matches(hw_product_id);
    -- 기존 매칭 데이터 클리어 (재실행시)
    DELETE FROM product_matches;
    """)
    con.commit()

    # canonical_brand 별로 채널 제품 묶기 (현 세션 ranking 기준)
    rows = cur.execute("""
        SELECT ba.canonical_brand, p.platform, p.id, p.product_name,
               rs.rank, rs.category, rs.sale_price, rs.rating, rs.review_score
        FROM ranking_snapshots rs
        JOIN products p ON p.id = rs.product_id
        JOIN brand_aliases ba ON ba.platform = p.platform AND ba.raw_brand = p.brand
        WHERE rs.session_id = ?
    """, (SESSION,)).fetchall()

    by_canon: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for canon, plat, pid, pname, rank, cat, price, rating, rscore in rows:
        norm = normalize(pname)
        if not norm:
            continue
        # 같은 product_id는 카테고리별 중복 가능 → 첫 등장만
        existing = next((x for x in by_canon[canon][plat] if x["id"] == pid), None)
        if existing:
            continue
        by_canon[canon][plat].append({
            "id": pid, "name": pname, "norm": norm,
            "rank": rank, "category": cat, "price": price,
            "rating": rating, "rscore": rscore,
        })

    # 3-way 매칭 가능한 canonical brand만 처리
    canonicals = sorted(by_canon.keys())
    print(f"매칭 대상 canonical brand: {len(canonicals)}")

    now = datetime.now(timezone.utc).isoformat()
    pair_matches: dict[tuple, dict] = {}  # (canon, plat_a, id_a, plat_b, id_b) -> info

    def best_match(items_a: list, items_b: list) -> list[tuple]:
        """그리디 1:1 — items_a 각각에 대해 items_b 최고 fuzzy → threshold 이상만."""
        used_b = set()
        out = []
        # 점수 순으로 처리해야 글로벌 그리디 근사
        candidates = []
        for a in items_a:
            for b in items_b:
                s = sim(a["norm"], b["norm"])
                if s >= THRESHOLD:
                    candidates.append((s, a, b))
        candidates.sort(key=lambda x: -x[0])
        used_a = set()
        for s, a, b in candidates:
            if a["id"] in used_a or b["id"] in used_b:
                continue
            used_a.add(a["id"])
            used_b.add(b["id"])
            out.append((a, b, s))
        return out

    pair_counts = {"oy_ms": 0, "oy_hw": 0, "ms_hw": 0}
    for canon in canonicals:
        plats = by_canon[canon]
        oy = plats.get("oliveyoung", [])
        ms = plats.get("musinsa", [])
        hw = plats.get("hwahae", [])

        for plat_a, items_a, plat_b, items_b, key in [
            ("oliveyoung", oy, "musinsa", ms, "oy_ms"),
            ("oliveyoung", oy, "hwahae", hw, "oy_hw"),
            ("musinsa", ms, "hwahae", hw, "ms_hw"),
        ]:
            if not items_a or not items_b:
                continue
            for a, b, s in best_match(items_a, items_b):
                pair_matches[(canon, plat_a, a["id"], plat_b, b["id"])] = {
                    "score": s, "key": key
                }
                pair_counts[key] += 1

    print(f"\nPair 매칭:")
    for k, v in pair_counts.items():
        print(f"  {k}: {v}")

    # 3-way 합치기: oy-ms와 oy-hw가 같은 oy를 공유하면 3-way
    by_oy: dict[int, dict] = {}  # oy_id -> {ms: id, hw: id, score_oy_ms, score_oy_hw, canon}
    for (canon, pa, ia, pb, ib), info in pair_matches.items():
        if info["key"] == "oy_ms":
            d = by_oy.setdefault(ia, {"canon": canon})
            d["ms_id"] = ib; d["score_oy_ms"] = info["score"]
        elif info["key"] == "oy_hw":
            d = by_oy.setdefault(ia, {"canon": canon})
            d["hw_id"] = ib; d["score_oy_hw"] = info["score"]

    # 적재
    inserted = {"3way": 0, "oy_ms_only": 0, "oy_hw_only": 0, "ms_hw_only": 0}

    used_oy_in_3way: set[int] = set()
    used_ms_in_3way: set[int] = set()
    used_hw_in_3way: set[int] = set()

    # 3-way 먼저
    for oy_id, d in by_oy.items():
        if "ms_id" in d and "hw_id" in d:
            score = (d["score_oy_ms"] + d["score_oy_hw"]) / 2
            cur.execute(
                """INSERT INTO product_matches
                   (canonical_brand, oy_product_id, ms_product_id, hw_product_id, match_score, match_method, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (d["canon"], oy_id, d["ms_id"], d["hw_id"], score, "name_fuzzy_3way", now),
            )
            inserted["3way"] += 1
            used_oy_in_3way.add(oy_id)
            used_ms_in_3way.add(d["ms_id"])
            used_hw_in_3way.add(d["hw_id"])

    # 2-way (3way에 안 든 페어만)
    for (canon, pa, ia, pb, ib), info in pair_matches.items():
        key = info["key"]
        if key == "oy_ms" and (ia in used_oy_in_3way or ib in used_ms_in_3way):
            continue
        if key == "oy_hw" and (ia in used_oy_in_3way or ib in used_hw_in_3way):
            continue
        if key == "ms_hw" and (ia in used_ms_in_3way or ib in used_hw_in_3way):
            continue
        if key == "oy_ms":
            cur.execute("""INSERT INTO product_matches
                (canonical_brand, oy_product_id, ms_product_id, match_score, match_method, created_at)
                VALUES (?,?,?,?,?,?)""", (canon, ia, ib, info["score"], "name_fuzzy_2way", now))
            inserted["oy_ms_only"] += 1
        elif key == "oy_hw":
            cur.execute("""INSERT INTO product_matches
                (canonical_brand, oy_product_id, hw_product_id, match_score, match_method, created_at)
                VALUES (?,?,?,?,?,?)""", (canon, ia, ib, info["score"], "name_fuzzy_2way", now))
            inserted["oy_hw_only"] += 1
        elif key == "ms_hw":
            cur.execute("""INSERT INTO product_matches
                (canonical_brand, ms_product_id, hw_product_id, match_score, match_method, created_at)
                VALUES (?,?,?,?,?,?)""", (canon, ia, ib, info["score"], "name_fuzzy_2way", now))
            inserted["ms_hw_only"] += 1

    con.commit()
    print(f"\n적재:")
    for k, v in inserted.items():
        print(f"  {k}: {v}")

    # 샘플 — 3-way 매칭 상위 10개 (점수순)
    print(f"\n=== 3-way 매칭 샘플 TOP 10 ===")
    for row in cur.execute("""
        SELECT pm.canonical_brand, pm.match_score,
               oy.product_name, ms.product_name, hw.product_name
        FROM product_matches pm
        LEFT JOIN products oy ON oy.id = pm.oy_product_id
        LEFT JOIN products ms ON ms.id = pm.ms_product_id
        LEFT JOIN products hw ON hw.id = pm.hw_product_id
        WHERE pm.match_method = 'name_fuzzy_3way'
        ORDER BY pm.match_score DESC LIMIT 10
    """):
        canon, score, oyn, msn, hwn = row
        print(f"  [{canon}] {score:.2f}")
        print(f"    OY: {(oyn or '-')[:60]}")
        print(f"    MS: {(msn or '-')[:60]}")
        print(f"    HW: {(hwn or '-')[:60]}")


if __name__ == "__main__":
    main()
