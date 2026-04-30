"""화해 중심 브랜드 매핑.

브랜드명 정규화 후 fuzzy match로 화해 ↔ OY ↔ MS 교집합 산출.
"""
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

from sqlalchemy import text

from src.models import get_engine, get_session

SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260430_231616"
THRESHOLD = 0.85

NON_ALNUM = re.compile(r"[^0-9a-z가-힣]+")

# 한↔영 / 표기 변형 alias. 표준명(화해 표기 우선)으로 통일.
BRAND_ALIAS = {
    # OY/MS 표기 → 표준 표기 (화해 기준)
    "캘빈클라인": "CK",
    "캘빈클라인 퍼퓸": "CK",
    "쓰리씨이": "3CE",
    "에이에이치씨": "AHC",
    "GNM자연의품격": "GNM",
    "랑방 퍼퓸": "랑방",
    "몽블랑 퍼퓸": "몽블랑",
    "헤트라스 뷰티": "헤트라스",
    "베르사체 퍼퓸": "베르사체",
    "메종 마르지엘라 퍼퓸": "메종 마르지엘라",
    "에르메스 어메니티": "에르메스",
    "정샘물": "정샘물뷰티",
    "로레알": "로레알파리",
    "로레알 프로페셔널": "로레알프로페셔널파리",
    "CKD": "CKDGUARANTEED",
}


def normalize(name: str) -> str:
    canonical = BRAND_ALIAS.get(name.strip(), name)
    s = canonical.strip().lower()
    return NON_ALNUM.sub("", s)


def fuzzy_match(target: str, candidates: list[str], threshold: float) -> str | None:
    best, best_score = None, 0.0
    for c in candidates:
        score = SequenceMatcher(None, target, c).ratio()
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= threshold else None


def main():
    engine = get_engine("data/beauty_ranking.db")
    db = get_session(engine)

    rows = db.execute(text("""
        SELECT p.platform, p.brand, COUNT(*) AS items
        FROM ranking_snapshots rs JOIN products p ON rs.product_id=p.id
        WHERE rs.session_id=:sid AND p.brand IS NOT NULL AND p.brand != ''
        GROUP BY p.platform, p.brand
    """), {"sid": SESSION}).fetchall()

    # platform -> {norm_brand: [(display_brand, items), ...]}
    by_plat: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for plat, brand, items in rows:
        norm = normalize(brand)
        if not norm:
            continue
        by_plat[plat][norm].append((brand, items))

    hw = by_plat["hwahae"]
    oy = by_plat["oliveyoung"]
    ms = by_plat["musinsa"]

    # 1단계: 정규화 exact match
    hw_oy_exact = set(hw) & set(oy)
    hw_ms_exact = set(hw) & set(ms)

    # 2단계: 남은 OY/MS 브랜드를 화해와 fuzzy
    hw_keys = list(hw.keys())
    oy_only = set(oy) - hw_oy_exact
    ms_only = set(ms) - hw_ms_exact

    hw_oy_fuzzy: dict[str, str] = {}
    for k in oy_only:
        m = fuzzy_match(k, hw_keys, THRESHOLD)
        if m:
            hw_oy_fuzzy[k] = m

    hw_ms_fuzzy: dict[str, str] = {}
    for k in ms_only:
        m = fuzzy_match(k, hw_keys, THRESHOLD)
        if m:
            hw_ms_fuzzy[k] = m

    # 화해 norm key 기준으로 4개 버킷 분류
    matched_in_oy = hw_oy_exact | set(hw_oy_fuzzy.values())
    matched_in_ms = hw_ms_exact | set(hw_ms_fuzzy.values())

    bucket_3way = matched_in_oy & matched_in_ms
    bucket_hw_oy = matched_in_oy - bucket_3way
    bucket_hw_ms = matched_in_ms - bucket_3way
    bucket_hw_only = set(hw_keys) - matched_in_oy - matched_in_ms

    def disp(plat_dict: dict, norm: str) -> str:
        entries = plat_dict.get(norm, [])
        return entries[0][0] if entries else "-"

    def items(plat_dict: dict, norm: str) -> int:
        return sum(i for _, i in plat_dict.get(norm, []))

    print(f"=== 세션 {SESSION} 화해 중심 브랜드 매핑 (threshold={THRESHOLD}) ===\n")
    print(f"화해 브랜드: {len(hw)} / 올영: {len(oy)} / 무신사: {len(ms)}")
    print(f"정규화 exact: 화해×올영={len(hw_oy_exact)}, 화해×무신사={len(hw_ms_exact)}")
    print(f"fuzzy 추가  : 화해×올영=+{len(hw_oy_fuzzy)}, 화해×무신사=+{len(hw_ms_fuzzy)}")
    print()
    print(f"버킷:")
    print(f"  3-way (화해+OY+MS) : {len(bucket_3way)}")
    print(f"  화해+올영만        : {len(bucket_hw_oy)}")
    print(f"  화해+무신사만      : {len(bucket_hw_ms)}")
    print(f"  화해 단독          : {len(bucket_hw_only)}")
    print()

    # 화해 norm -> oy/ms norm 역매핑
    oy_match_for_hw: dict[str, str] = {}
    for n in hw_oy_exact:
        oy_match_for_hw[n] = n
    for oy_n, hw_n in hw_oy_fuzzy.items():
        oy_match_for_hw[hw_n] = oy_n

    ms_match_for_hw: dict[str, str] = {}
    for n in hw_ms_exact:
        ms_match_for_hw[n] = n
    for ms_n, hw_n in hw_ms_fuzzy.items():
        ms_match_for_hw[hw_n] = ms_n

    print("=== 3-way 매핑 (화해 / 올영 / 무신사 / 상품수 hw|oy|ms) ===")
    rows_3way = []
    for n in bucket_3way:
        rows_3way.append((
            disp(hw, n), disp(oy, oy_match_for_hw[n]), disp(ms, ms_match_for_hw[n]),
            items(hw, n), items(oy, oy_match_for_hw[n]), items(ms, ms_match_for_hw[n]),
        ))
    rows_3way.sort(key=lambda r: -(r[3] + r[4] + r[5]))
    for r in rows_3way:
        print(f"  {r[0]:20s} | {r[1]:20s} | {r[2]:20s} | {r[3]:3d}|{r[4]:3d}|{r[5]:3d}")

    print(f"\n=== 화해+올영만 (무신사 미입점) 전체 {len(bucket_hw_oy)}개 ===")
    rows_hwoy = [(disp(hw, n), disp(oy, oy_match_for_hw[n]), items(hw, n), items(oy, oy_match_for_hw[n])) for n in bucket_hw_oy]
    rows_hwoy.sort(key=lambda r: -(r[2] + r[3]))
    for r in rows_hwoy:
        print(f"  {r[0]:20s} | {r[1]:20s} | hw={r[2]:3d}, oy={r[3]:3d}")

    print(f"\n=== 화해+무신사만 (올영 미입점) 전체 {len(bucket_hw_ms)}개 ===")
    rows_hwms = [(disp(hw, n), disp(ms, ms_match_for_hw[n]), items(hw, n), items(ms, ms_match_for_hw[n])) for n in bucket_hw_ms]
    rows_hwms.sort(key=lambda r: -(r[2] + r[3]))
    for r in rows_hwms:
        print(f"  {r[0]:20s} | {r[1]:20s} | hw={r[2]:3d}, ms={r[3]:3d}")

    print(f"\n=== 화해 단독 전체 {len(bucket_hw_only)}개 (상품수 기준 정렬) ===")
    rows_hw_only = [(disp(hw, n), items(hw, n)) for n in bucket_hw_only]
    rows_hw_only.sort(key=lambda r: -r[1])
    for r in rows_hw_only:
        print(f"  {r[0]:20s} | hw={r[1]:3d}")

    # 화해와 매핑 안 된 OY/MS 브랜드
    matched_oy_norms = set(oy_match_for_hw.values())
    matched_ms_norms = set(ms_match_for_hw.values())
    oy_unmatched = [(disp(oy, n), items(oy, n)) for n in oy if n not in matched_oy_norms]
    ms_unmatched = [(disp(ms, n), items(ms, n)) for n in ms if n not in matched_ms_norms]
    oy_unmatched.sort(key=lambda r: -r[1])
    ms_unmatched.sort(key=lambda r: -r[1])

    print(f"\n=== 올영 단독 (화해 매핑 없음) 전체 {len(oy_unmatched)}개 ===")
    for r in oy_unmatched:
        print(f"  {r[0]:20s} | oy={r[1]:3d}")

    print(f"\n=== 무신사 단독 (화해 매핑 없음) 전체 {len(ms_unmatched)}개 ===")
    for r in ms_unmatched:
        print(f"  {r[0]:20s} | ms={r[1]:3d}")


if __name__ == "__main__":
    main()
