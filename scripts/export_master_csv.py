"""마스터 CSV 추출 — 수동 분석용.

출력:
  data/exports/products_master.csv  : 채널별 제품 long format
  data/exports/matches_wide.csv     : 매칭 그룹 wide format (3채널 나란히)
"""
import csv
import sqlite3
import sys
from pathlib import Path

DB = "data/beauty_ranking.db"
SESSION = sys.argv[1] if len(sys.argv) > 1 else "20260430_231616"
OUT_DIR = Path("data/exports")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def export_long():
    """채널별 제품 long. 최신 세션의 ranking_snapshot 정보 + 성분/효능 카운트."""
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 최신 세션의 best rank/대표 카테고리/가격 등 (제품당 1행 ⇒ 카테고리 다중 노출 시 best rank)
    rows = cur.execute("""
        WITH best AS (
            SELECT rs.product_id,
                   MIN(rs.rank) AS best_rank,
                   GROUP_CONCAT(DISTINCT rs.category) AS categories,
                   AVG(rs.sale_price) AS avg_sale_price,
                   AVG(rs.original_price) AS avg_original_price,
                   AVG(rs.rating) AS rating,
                   AVG(rs.review_score) AS review_score,
                   SUM(rs.review_count) AS review_count
            FROM ranking_snapshots rs
            WHERE rs.session_id = ?
            GROUP BY rs.product_id
        ),
        ing_count AS (
            SELECT product_id, COUNT(*) AS ingredient_count,
                   SUM(CASE WHEN i.is_allergy=1 THEN 1 ELSE 0 END) AS allergy_count,
                   SUM(CASE WHEN i.is_twenty=1 THEN 1 ELSE 0 END) AS twenty_count,
                   SUM(CASE WHEN i.ewg IN ('7','8','9','10') THEN 1 ELSE 0 END) AS ewg_high_count
            FROM product_ingredients pi
            JOIN ingredients i ON i.id = pi.ingredient_id
            GROUP BY product_id
        ),
        eff_count AS (
            SELECT product_id,
                   SUM(score) AS effect_score_total,
                   COUNT(*) AS effect_count
            FROM product_effects GROUP BY product_id
        ),
        match_grp AS (
            SELECT id AS group_id, oy_product_id AS pid, 'oliveyoung' AS plat,
                   match_method, match_score FROM product_matches
            UNION ALL
            SELECT id, ms_product_id, 'musinsa', match_method, match_score FROM product_matches
            UNION ALL
            SELECT id, hw_product_id, 'hwahae', match_method, match_score FROM product_matches
        )
        SELECT
            p.platform, p.product_id AS channel_pid, p.brand AS raw_brand,
            ba.canonical_brand, p.product_name,
            b.best_rank, b.categories,
            CAST(b.avg_original_price AS INTEGER) AS original_price,
            CAST(b.avg_sale_price AS INTEGER) AS sale_price,
            ROUND(b.rating, 2) AS rating,
            CAST(b.review_score AS INTEGER) AS review_score,
            b.review_count,
            COALESCE(ic.ingredient_count, 0) AS ingredient_count,
            COALESCE(ic.allergy_count, 0) AS allergy_count,
            COALESCE(ic.twenty_count, 0) AS twenty_count,
            COALESCE(ic.ewg_high_count, 0) AS ewg_high_count,
            COALESCE(ec.effect_count, 0) AS effect_count,
            COALESCE(ec.effect_score_total, 0) AS effect_score_total,
            mg.group_id AS match_group_id,
            mg.match_method,
            mg.match_score,
            p.first_seen_at, p.last_seen_at
        FROM products p
        JOIN best b ON b.product_id = p.id
        LEFT JOIN brand_aliases ba ON ba.platform = p.platform AND ba.raw_brand = p.brand
        LEFT JOIN ing_count ic ON ic.product_id = p.id
        LEFT JOIN eff_count ec ON ec.product_id = p.id
        LEFT JOIN match_grp mg ON mg.pid = p.id AND mg.plat = p.platform
        ORDER BY ba.canonical_brand, p.platform, b.best_rank
    """, (SESSION,)).fetchall()

    cols = [
        "platform", "channel_pid", "raw_brand", "canonical_brand", "product_name",
        "best_rank", "categories", "original_price", "sale_price",
        "rating", "review_score", "review_count",
        "ingredient_count", "allergy_count", "twenty_count", "ewg_high_count",
        "effect_count", "effect_score_total",
        "match_group_id", "match_method", "match_score",
        "first_seen_at", "last_seen_at",
    ]
    out = OUT_DIR / "products_master.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print(f"long format: {out} ({len(rows)} rows)")


def export_wide():
    """매칭 그룹 wide. 3채널 나란히 + 핵심 메트릭."""
    con = sqlite3.connect(DB)
    cur = con.cursor()

    rows = cur.execute("""
        SELECT
            pm.id, pm.canonical_brand, pm.match_method, pm.match_score,
            oy.product_name, oy.product_id,
            ms.product_name, ms.product_id,
            hw.product_name, hw.product_id,
            -- 최신 세션 메트릭
            (SELECT MIN(rank) FROM ranking_snapshots WHERE session_id=? AND product_id=oy.id) AS oy_rank,
            (SELECT MIN(rank) FROM ranking_snapshots WHERE session_id=? AND product_id=ms.id) AS ms_rank,
            (SELECT MIN(rank) FROM ranking_snapshots WHERE session_id=? AND product_id=hw.id) AS hw_rank,
            (SELECT AVG(sale_price) FROM ranking_snapshots WHERE session_id=? AND product_id=oy.id) AS oy_price,
            (SELECT AVG(sale_price) FROM ranking_snapshots WHERE session_id=? AND product_id=ms.id) AS ms_price,
            (SELECT AVG(sale_price) FROM ranking_snapshots WHERE session_id=? AND product_id=hw.id) AS hw_price,
            (SELECT AVG(rating) FROM ranking_snapshots WHERE session_id=? AND product_id=oy.id) AS oy_rating,
            (SELECT AVG(review_score) FROM ranking_snapshots WHERE session_id=? AND product_id=ms.id) AS ms_rscore,
            (SELECT AVG(rating) FROM ranking_snapshots WHERE session_id=? AND product_id=hw.id) AS hw_rating,
            (SELECT AVG(review_score) FROM ranking_snapshots WHERE session_id=? AND product_id=hw.id) AS hw_rscore,
            (SELECT COUNT(*) FROM product_ingredients WHERE product_id=hw.id) AS hw_ingredient_count,
            (SELECT GROUP_CONCAT(e.name || ':' || pe.score, '|')
                FROM product_effects pe JOIN effects e ON e.id=pe.effect_id WHERE pe.product_id=hw.id) AS hw_effects
        FROM product_matches pm
        LEFT JOIN products oy ON oy.id = pm.oy_product_id
        LEFT JOIN products ms ON ms.id = pm.ms_product_id
        LEFT JOIN products hw ON hw.id = pm.hw_product_id
        ORDER BY pm.match_method, pm.match_score DESC
    """, (SESSION,) * 10).fetchall()

    cols = [
        "match_id", "canonical_brand", "match_method", "match_score",
        "oy_name", "oy_pid", "ms_name", "ms_pid", "hw_name", "hw_pid",
        "oy_rank", "ms_rank", "hw_rank",
        "oy_price", "ms_price", "hw_price",
        "oy_rating", "ms_review_score", "hw_rating", "hw_review_score",
        "hw_ingredient_count", "hw_effects",
    ]
    out = OUT_DIR / "matches_wide.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            # round prices/ratings
            r = list(r)
            for i in (13, 14, 15):  # prices
                r[i] = int(r[i]) if r[i] is not None else ""
            for i in (16, 17, 18, 19):  # ratings/scores
                r[i] = round(r[i], 2) if r[i] is not None else ""
            w.writerow(r)
    print(f"wide format: {out} ({len(rows)} rows)")


if __name__ == "__main__":
    export_long()
    export_wide()
