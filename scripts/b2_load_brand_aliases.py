"""B2-light: brand_aliases 테이블 생성 + 적재.

소스:
1. BRAND_ALIAS dict (alias_dict, 14건)
2. B1 STRONG 결과 (lookup_strong, 146건)
3. NOISE 정밀검토 회수 케이스 (lookup_noise_resolved, 수동 정의)
4. 화해 자체 (canonical = raw, source='self')
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = "data/beauty_ranking.db"
LOOKUP_JSON = Path("data/_recon/hwahae_brand_lookup.json")

BRAND_ALIAS = {
    "캘빈클라인": "CK", "캘빈클라인 퍼퓸": "CK", "쓰리씨이": "3CE",
    "에이에이치씨": "AHC", "GNM자연의품격": "GNM", "랑방 퍼퓸": "랑방",
    "몽블랑 퍼퓸": "몽블랑", "헤트라스 뷰티": "헤트라스", "베르사체 퍼퓸": "베르사체",
    "메종 마르지엘라 퍼퓸": "메종 마르지엘라", "에르메스 어메니티": "에르메스",
    "정샘물": "정샘물뷰티", "로레알": "로레알파리",
    "로레알 프로페셔널": "로레알프로페셔널파리", "CKD": "CKDGUARANTEED",
}

# B1 NOISE 정밀검토 — top_label 한글 부분이 raw_brand와 사실상 동일하거나
# 명확한 표기차/서브라인인 경우 회수 (canonical은 화해의 top_label 한글).
NOISE_RESOLVED = {
    # raw_brand: hwahae_canonical_label (영문 표기 떼고 한글만)
    "제이엠더블유": "JMW",                # JMW (제이엠더블유)
    "리쥬더마 EX": "리쥬더마 이엑스",      # REJUDERMA EX
    "오피아이": "OPI",                    # OPI (오피아이)
    "오프라 코스메틱": "오프라",          # OFRA
    "시코르 컬렉션": "시코르",            # CHICOR
    "메모": "메모파리",                    # MEMOPARIS
    "엔트로피 메이크업": "엔트로피",      # ENTROPY
    "리쥬란": "리쥬란코스메틱",            # REJURANCOSMETICS
    "메디큐브 에이지알": "메디큐브",       # 본가에 흡수 (서브라인)
    "폴로랄프로렌 퍼퓸": "랄프로렌",       # 본가
    "에스더블유나인틴": "SW19",            # SW19
    "리브러쉬": "러쉬",                    # 본가 LUSH
    "코카-콜라": "립스매커",               # 콜라 라인 → 립스매커 콜라보
    "캐치 티니핑 뷰티": "참존",            # 콜라보 SKU
}


def normalize_kor(label: str) -> str:
    """'JMW (제이엠더블유)' → 'JMW' / '코링코 (CORINGCO)' → '코링코' (괄호 제거)."""
    return re.sub(r"\([^)]*\)", "", label or "").strip()


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS brand_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        raw_brand TEXT NOT NULL,
        canonical_brand TEXT NOT NULL,
        source TEXT NOT NULL,
        confidence REAL,
        created_at TEXT NOT NULL,
        UNIQUE(platform, raw_brand)
    );
    CREATE INDEX IF NOT EXISTS idx_ba_canonical ON brand_aliases(canonical_brand);
    """)
    con.commit()

    now = datetime.now(timezone.utc).isoformat()
    rows: list[tuple] = []

    # 1. 모든 채널 self (brand 표기 그대로 canonical로 1차 매핑)
    #    이후 alias_dict / lookup_strong / lookup_noise_resolved이 OVERRIDE (REPLACE)
    for plat in ("hwahae", "oliveyoung", "musinsa"):
        for (brand,) in cur.execute(
            "SELECT DISTINCT brand FROM products WHERE platform=? AND brand IS NOT NULL AND brand!=''",
            (plat,),
        ):
            rows.append((plat, brand, brand, "self", 1.0, now))

    # 2. alias dict (OY/MS 채널 raw → 화해 canonical)
    # raw_brand는 OY 또는 MS의 실제 표기. alias_dict는 양 채널 공통 사용
    for raw, canonical in BRAND_ALIAS.items():
        for plat in ("oliveyoung", "musinsa"):
            exists = cur.execute(
                "SELECT 1 FROM products WHERE platform=? AND brand=? LIMIT 1", (plat, raw)
            ).fetchone()
            if exists:
                rows.append((plat, raw, canonical, "alias_dict", 1.0, now))

    # 3. B1 STRONG
    lookups = json.loads(LOOKUP_JSON.read_text())
    src_to_plats = {"OY": ["oliveyoung"], "MS": ["musinsa"], "OY+MS": ["oliveyoung", "musinsa"]}

    for r in lookups:
        if r["verdict"] != "STRONG":
            continue
        canonical = normalize_kor(r["top_label"])
        for plat in src_to_plats.get(r["source"], []):
            exists = cur.execute(
                "SELECT 1 FROM products WHERE platform=? AND brand=? LIMIT 1", (plat, r["brand"])
            ).fetchone()
            if exists:
                conf = r["exact_in_page"] / max(r["page_size_n"], 1)
                rows.append((plat, r["brand"], canonical, "lookup_strong", conf, now))

    # 4. NOISE 정밀검토 회수
    for r in lookups:
        if r["verdict"] != "NOISE":
            continue
        if r["brand"] not in NOISE_RESOLVED:
            continue
        canonical = NOISE_RESOLVED[r["brand"]]
        for plat in src_to_plats.get(r["source"], []):
            exists = cur.execute(
                "SELECT 1 FROM products WHERE platform=? AND brand=? LIMIT 1", (plat, r["brand"])
            ).fetchone()
            if exists:
                rows.append((plat, r["brand"], canonical, "lookup_noise_resolved", 0.7, now))

    # bulk insert
    cur.executemany(
        """INSERT OR REPLACE INTO brand_aliases
           (platform, raw_brand, canonical_brand, source, confidence, created_at)
           VALUES (?,?,?,?,?,?)""",
        rows,
    )
    con.commit()

    # 요약
    print(f"적재: {len(rows)}건")
    by_src = cur.execute(
        "SELECT source, COUNT(*) FROM brand_aliases GROUP BY source"
    ).fetchall()
    for s, c in by_src:
        print(f"  {s}: {c}")

    by_plat = cur.execute(
        "SELECT platform, COUNT(*) FROM brand_aliases GROUP BY platform"
    ).fetchall()
    print()
    for p, c in by_plat:
        print(f"  {p}: {c}")

    # 매칭 풀 검증: canonical_brand 기준 3-way 교집합
    three_way = cur.execute("""
        SELECT canonical_brand FROM brand_aliases
        GROUP BY canonical_brand
        HAVING SUM(platform='hwahae') > 0
           AND SUM(platform='oliveyoung') > 0
           AND SUM(platform='musinsa') > 0
    """).fetchall()
    two_way_oy = cur.execute("""
        SELECT canonical_brand FROM brand_aliases
        GROUP BY canonical_brand
        HAVING SUM(platform='hwahae') > 0
           AND SUM(platform='oliveyoung') > 0
           AND SUM(platform='musinsa') = 0
    """).fetchall()
    two_way_ms = cur.execute("""
        SELECT canonical_brand FROM brand_aliases
        GROUP BY canonical_brand
        HAVING SUM(platform='hwahae') > 0
           AND SUM(platform='musinsa') > 0
           AND SUM(platform='oliveyoung') = 0
    """).fetchall()

    print()
    print(f"=== canonical_brand 기준 매칭 풀 ===")
    print(f"  3-way (HW+OY+MS): {len(three_way)}")
    print(f"  HW+OY만         : {len(two_way_oy)}")
    print(f"  HW+MS만         : {len(two_way_ms)}")


if __name__ == "__main__":
    main()
