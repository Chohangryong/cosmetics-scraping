import logging
from datetime import datetime

from sqlalchemy import text

from src.models import (
    Product,
    RankingSnapshot,
    RankingItem,
    get_engine,
    create_tables,
    migrate_db,
    get_session,
)

log = logging.getLogger(__name__)


def save_to_db(
    items: list[dict],
    session_id: str,
    db_path: str = "data/beauty_ranking.db",
) -> int:
    """Spider 결과를 DB에 저장.

    Returns:
        저장된 ranking_snapshots 건수
    """
    engine = get_engine(db_path)
    create_tables(engine)
    migrate_db(engine)
    db = get_session(engine)
    now = datetime.now().isoformat()
    saved = 0

    try:
        with db.begin():
            for raw in items:
                item = RankingItem(**raw)

                # 1. products upsert
                db.execute(
                    text(
                        "INSERT OR IGNORE INTO products "
                        "(platform, product_id, product_name, brand, first_seen_at, last_seen_at) "
                        "VALUES (:platform, :product_id, :name, :brand, :now, :now)"
                    ),
                    {
                        "platform": item.platform,
                        "product_id": item.product_id,
                        "name": item.name,
                        "brand": item.brand,
                        "now": now,
                    },
                )
                # last_seen_at 갱신
                db.execute(
                    text(
                        "UPDATE products SET last_seen_at = :now, product_name = :name "
                        "WHERE platform = :platform AND product_id = :product_id"
                    ),
                    {
                        "now": now,
                        "name": item.name,
                        "platform": item.platform,
                        "product_id": item.product_id,
                    },
                )

                # 2. products.id 조회
                row = db.execute(
                    text(
                        "SELECT id FROM products "
                        "WHERE platform = :platform AND product_id = :product_id"
                    ),
                    {"platform": item.platform, "product_id": item.product_id},
                ).fetchone()
                pk = row[0]

                # 3. ranking_snapshots INSERT
                db.execute(
                    text(
                        "INSERT INTO ranking_snapshots "
                        "(session_id, product_id, platform, category, rank, "
                        "original_price, sale_price, discount_rate, rating, review_count, badge, collected_at) "
                        "VALUES (:session_id, :product_id, :platform, :category, :rank, "
                        ":original_price, :sale_price, :discount_rate, :rating, :review_count, :badge, :collected_at)"
                    ),
                    {
                        "session_id": session_id,
                        "product_id": pk,
                        "platform": item.platform,
                        "category": item.category,
                        "rank": item.rank,
                        "original_price": item.original_price,
                        "sale_price": item.sale_price,
                        "discount_rate": item.discount_rate,
                        "rating": item.rating,
                        "review_count": item.review_count,
                        "badge": item.badge,
                        "collected_at": now,
                    },
                )
                saved += 1

    except Exception as e:
        log.error(f"DB 저장 실패: {e}")
        raise

    log.info(f"DB 저장 완료: {saved}건 (session: {session_id})")
    return saved


def update_ratings(
    product_id: str,
    session_id: str,
    rating: float | None,
    review_count: int | None,
    db_path: str = "data/beauty_ranking.db",
) -> None:
    """상세 페이지에서 수집한 rating + review_count를 ranking_snapshots에 업데이트"""
    engine = get_engine(db_path)
    db = get_session(engine)
    with db.begin():
        db.execute(
            text(
                "UPDATE ranking_snapshots "
                "SET rating = :rating, review_count = :review_count "
                "WHERE session_id = :session_id "
                "AND product_id = ("
                "  SELECT id FROM products "
                "  WHERE product_id = :ext_id AND platform = 'oliveyoung'"  # TODO: platform 파라미터화 필요 (무신사 rating 보강 시)
                ")"
            ),
            {
                "rating": rating,
                "review_count": review_count,
                "session_id": session_id,
                "ext_id": product_id,
            },
        )
