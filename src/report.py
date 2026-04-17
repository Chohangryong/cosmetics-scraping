import argparse
import csv
import sys
from collections import defaultdict

from sqlalchemy import text

from src.models import get_engine, get_session

CATEGORY_ORDER = ["skincare", "makeup", "suncare"]
BAR = "━" * 68
SEP = "─" * 68


# ── 유틸 ──────────────────────────────────────────────

def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_change(curr_rank: int, prev_rank: int | None) -> str:
    if prev_rank is None:
        return "🆕"
    d = prev_rank - curr_rank  # 양수 = 순위 상승
    if d == 0:
        return "→"
    return f"↑{d}" if d > 0 else f"↓{abs(d)}"


def fmt_price(price: int | None) -> str:
    return f"{price:,}원" if price else "-"


# ── DB 조회 ───────────────────────────────────────────

def get_sessions(db, platform: str, n: int = 2) -> list[str]:
    rows = db.execute(
        text(
            "SELECT DISTINCT session_id FROM ranking_snapshots "
            "WHERE platform = :platform ORDER BY session_id DESC LIMIT :n"
        ),
        {"platform": platform, "n": n},
    ).fetchall()
    return [r[0] for r in rows]


def load_session(db, session_id: str, platform: str) -> dict[str, dict]:
    """반환: {category: {ext_product_id: row_dict}}"""
    rows = db.execute(
        text(
            "SELECT rs.category, rs.rank, rs.sale_price, rs.discount_rate, "
            "rs.rating, rs.review_count, rs.badge, "
            "p.product_id AS ext_id, p.product_name AS name, p.brand "
            "FROM ranking_snapshots rs "
            "JOIN products p ON rs.product_id = p.id "
            "WHERE rs.session_id = :sid AND rs.platform = :platform"
        ),
        {"sid": session_id, "platform": platform},
    )
    result: dict[str, dict] = defaultdict(dict)
    for r in rows:
        m = dict(r._mapping)
        result[m["category"]][m["ext_id"]] = m
    return result


# ── 리포트 출력 ────────────────────────────────────────

def print_report(curr, prev, curr_sid, prev_sid, top_brands: int = 10):
    date_curr = f"{curr_sid[:4]}-{curr_sid[4:6]}-{curr_sid[6:8]}"
    date_prev = f"{prev_sid[:4]}-{prev_sid[4:6]}-{prev_sid[6:8]}" if prev_sid else None
    date_label = f"{date_prev} → {date_curr}" if date_prev else date_curr

    products_rows = []
    brands_rows = []
    new_out_items = []  # 섹션 ② 용

    # ── 섹션 ① 순위 변화 ──────────────────────────────
    print(f"\n{BAR}")
    print(f"  ① 순위 변화   ({date_label})")
    print(BAR)
    print(f"  {'카테고리':<10} {'순위':>4}  {'변화':<5}  {'브랜드':<14}  {'상품명':<26}  {'가격':>9}")
    print(SEP)

    for cat in CATEGORY_ORDER:
        curr_cat = curr.get(cat, {})
        prev_cat = prev.get(cat, {}) if prev else {}

        # 현재 세션 상품 (순위순)
        for item in sorted(curr_cat.values(), key=lambda x: x["rank"]):
            pid = item["ext_id"]
            prev_rank = prev_cat.get(pid, {}).get("rank") if prev else None
            change = fmt_change(item["rank"], prev_rank)
            print(
                f"  {cat:<10} {item['rank']:>4}  {change:<5}  "
                f"{trunc(item['brand'], 14):<14}  "
                f"{trunc(item['name'], 26):<26}  {fmt_price(item['sale_price']):>9}"
            )
            # CSV 행 누적
            prev_r = prev_cat.get(pid, {}).get("rank") if prev else None
            if not prev:
                status = "N/A"
            elif pid not in prev_cat:
                status = "NEW"
            elif prev_r == item["rank"]:
                status = "SAME"
            elif prev_r > item["rank"]:
                status = "UP"
            else:
                status = "DOWN"

            products_rows.append({
                "platform": "oliveyoung",
                "category": cat,
                "rank_current": item["rank"],
                "rank_prev": prev_r,
                "change": (prev_r - item["rank"]) if prev_r is not None else None,
                "status": status,
                "brand": item["brand"],
                "name": item["name"],
                "sale_price": item["sale_price"],
                "discount_rate": item["discount_rate"],
                "rating": item["rating"],
                "review_count": item["review_count"],
                "badge": item["badge"],
                "session_current": curr_sid,
                "session_prev": prev_sid,
            })
            if prev and pid not in prev_cat:
                new_out_items.append({**item, "cat": cat, "status": "NEW", "prev_rank": None})

        # OUT 항목
        if prev:
            for pid, pitem in prev_cat.items():
                if pid not in curr_cat:
                    print(
                        f"  {cat:<10} {'OUT':>4}  {'💨':<5}  "
                        f"{trunc(pitem['brand'], 14):<14}  "
                        f"{trunc(pitem['name'], 26):<26}  "
                        f"{'(전 '+str(pitem['rank'])+'위)':>9}"
                    )
                    products_rows.append({
                        "platform": "oliveyoung",
                        "category": cat,
                        "rank_current": None,
                        "rank_prev": pitem["rank"],
                        "change": None,
                        "status": "OUT",
                        "brand": pitem["brand"],
                        "name": pitem["name"],
                        "sale_price": pitem.get("sale_price"),
                        "discount_rate": pitem.get("discount_rate"),
                        "rating": pitem.get("rating"),
                        "review_count": pitem.get("review_count"),
                        "badge": pitem.get("badge"),
                        "session_current": curr_sid,
                        "session_prev": prev_sid,
                    })
                    new_out_items.append({**pitem, "cat": cat, "status": "OUT", "prev_rank": pitem["rank"]})

    # ── 섹션 ② 신규 진입 / 이탈 ──────────────────────
    print(f"\n{BAR}")
    print(f"  ② 신규 진입 / 이탈")
    print(BAR)

    if not prev:
        print("  (이전 세션 없음 — 다음 수집 후 표시됩니다)")
    else:
        new_items = [r for r in new_out_items if r["status"] == "NEW"]
        out_items = [r for r in new_out_items if r["status"] == "OUT"]

        if not new_items and not out_items:
            print("  신규 진입 / 이탈 없음")
        else:
            print(f"  {'상태':<7}  {'카테고리':<10}  {'브랜드':<14}  {'상품명':<26}  {'순위':>6}")
            print(SEP)
            for item in sorted(new_items, key=lambda x: x["rank"]):
                print(
                    f"  {'🆕 NEW':<7}  {item['cat']:<10}  "
                    f"{trunc(item['brand'], 14):<14}  "
                    f"{trunc(item['name'], 26):<26}  → {item['rank']:>3}위"
                )
            for item in sorted(out_items, key=lambda x: x["prev_rank"]):
                print(
                    f"  {'💨 OUT':<7}  {item['cat']:<10}  "
                    f"{trunc(item['brand'], 14):<14}  "
                    f"{trunc(item['name'], 26):<26}  "
                    f"전 {item['prev_rank']:>3}위"
                )

    # ── 섹션 ③ 브랜드별 성적표 ────────────────────────
    print(f"\n{BAR}")
    print(f"  ③ 브랜드별 성적표  (TOP50 기준 · 이번주 제품 수 많은 순)")
    print(BAR)
    print(f"  {'카테고리':<10}  {'브랜드':<16}  {'이번주':>6}  {'지난주':>6}  {'변화':>6}  {'평균순위':>6}")
    print(SEP)

    for cat in CATEGORY_ORDER:
        curr_cat = curr.get(cat, {})
        prev_cat = prev.get(cat, {}) if prev else {}

        curr_brands: dict[str, list] = defaultdict(list)
        for item in curr_cat.values():
            curr_brands[item["brand"]].append(item["rank"])

        prev_brands: dict[str, list] = defaultdict(list)
        if prev:
            for item in prev_cat.values():
                prev_brands[item["brand"]].append(item["rank"])

        for brand, ranks in sorted(curr_brands.items(), key=lambda x: -len(x[1]))[:top_brands]:
            cnt_c = len(ranks)
            cnt_p = len(prev_brands.get(brand, [])) if prev else None
            diff = (cnt_c - cnt_p) if cnt_p is not None else None
            diff_str = f"{diff:+d}개" if diff is not None else "-"
            avg = f"{sum(ranks)/cnt_c:.1f}위"
            prev_str = f"{cnt_p}개" if cnt_p is not None else "-"
            print(
                f"  {cat:<10}  {trunc(brand, 16):<16}  {cnt_c:>4}개  "
                f"{prev_str:>5}  {diff_str:>6}  {avg:>6}"
            )
            brands_rows.append({
                "category": cat,
                "brand": brand,
                "count_current": cnt_c,
                "count_prev": cnt_p,
                "count_change": diff,
                "avg_rank_current": round(sum(ranks) / cnt_c, 1),
            })

    # ── 섹션 ④ 리뷰수 TOP N ──────────────────────────
    all_items = [
        item
        for cat in CATEGORY_ORDER
        for item in curr.get(cat, {}).values()
        if item.get("review_count") is not None
    ]
    if all_items:
        print(f"\n{BAR}")
        print(f"  ④ 리뷰수 TOP{top_brands}  (리뷰 많은 순)")
        print(BAR)
        print(f"  {'카테고리':<10}  {'순위':>4}  {'브랜드':<14}  {'상품명':<26}  {'평점':>5}  {'리뷰수':>8}")
        print(SEP)
        for item in sorted(all_items, key=lambda x: -(x["review_count"] or 0))[:top_brands]:
            rating_str = f"★{item['rating']}" if item.get("rating") else "-"
            print(
                f"  {item['category']:<10}  "
                f"{item['rank']:>4}  {trunc(item['brand'], 14):<14}  "
                f"{trunc(item['name'], 26):<26}  {rating_str:>5}  "
                f"{item['review_count']:>8,}건"
            )

    return products_rows, brands_rows


# ── CSV 저장 ──────────────────────────────────────────

def save_csvs(products_rows, brands_rows, date_str: str):
    p_path = f"data/report_{date_str}_products.csv"
    b_path = f"data/report_{date_str}_brands.csv"

    for path, rows in [(p_path, products_rows), (b_path, brands_rows)]:
        if rows:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

    print(f"\n  저장됨:")
    print(f"    {p_path}")
    print(f"    {b_path}")


# ── 진입점 ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="뷰티 랭킹 변화 리포트")
    parser.add_argument("--platform", default="oliveyoung", choices=["oliveyoung", "musinsa"])
    parser.add_argument("--csv", action="store_true", help="CSV 파일 저장")
    parser.add_argument("--top", type=int, default=10, metavar="N", help="섹션 ③ 브랜드 상위 N개 (기본 10)")
    parser.add_argument("--db", default="data/beauty_ranking.db")
    args = parser.parse_args()

    engine = get_engine(args.db)
    db = get_session(engine)

    sessions = get_sessions(db, args.platform)
    if not sessions:
        print("수집 데이터가 없습니다.")
        sys.exit(1)

    curr_sid = sessions[0]
    prev_sid = sessions[1] if len(sessions) >= 2 else None

    if not prev_sid:
        print(f"\n⚠  세션 1개 ({curr_sid[:8]}) — 비교하려면 1회 더 수집하세요.")
        print("   현재 랭킹을 표시합니다. (변화 지표 없음)")

    curr = load_session(db, curr_sid, args.platform)
    prev = load_session(db, prev_sid, args.platform) if prev_sid else None

    products_rows, brands_rows = print_report(curr, prev, curr_sid, prev_sid, top_brands=args.top)

    if args.csv:
        save_csvs(products_rows, brands_rows, curr_sid[:8])


if __name__ == "__main__":
    main()
