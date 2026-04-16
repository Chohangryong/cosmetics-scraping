import os
import tempfile

import pytest

from src.storage import save_to_db
from src.models import get_engine, create_tables, get_session


@pytest.fixture
def tmp_db():
    """임시 SQLite DB 파일 생성 및 정리"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def _make_item(platform="oliveyoung", product_id="A000001", rank=1, **kwargs):
    base = {
        "platform": platform,
        "category": "skincare",
        "product_id": product_id,
        "rank": rank,
        "brand": "테스트브랜드",
        "name": "테스트상품",
        "original_price": 30000,
        "sale_price": 21900,
        "discount_rate": None,
        "rating": 4.5,
        "badge": "세일",
    }
    base.update(kwargs)
    return base


class TestSaveToDb:
    def test_save_normal(self, tmp_db):
        items = [_make_item(product_id=f"P{i}", rank=i) for i in range(1, 11)]
        saved = save_to_db(items, session_id="20260416_090000", db_path=tmp_db)
        assert saved == 10

    def test_save_empty_list(self, tmp_db):
        saved = save_to_db([], session_id="20260416_090000", db_path=tmp_db)
        assert saved == 0

    def test_products_upsert(self, tmp_db):
        """같은 product_id 두 번 저장 시 products는 1건, snapshots는 2건"""
        item = _make_item(product_id="A000001", rank=1)
        save_to_db([item], session_id="session1", db_path=tmp_db)
        save_to_db([item], session_id="session2", db_path=tmp_db)

        engine = get_engine(tmp_db)
        db = get_session(engine)
        from sqlalchemy import text
        products = db.execute(text("SELECT COUNT(*) FROM products")).scalar()
        snapshots = db.execute(text("SELECT COUNT(*) FROM ranking_snapshots")).scalar()
        db.close()

        assert products == 1
        assert snapshots == 2

    def test_last_seen_at_updated(self, tmp_db):
        """재실행 시 last_seen_at이 갱신됨"""
        item = _make_item(product_id="A000001")
        save_to_db([item], session_id="session1", db_path=tmp_db)

        engine = get_engine(tmp_db)
        db = get_session(engine)
        from sqlalchemy import text
        first = db.execute(
            text("SELECT last_seen_at FROM products WHERE product_id = 'A000001'")
        ).scalar()
        db.close()

        # 두 번째 저장
        save_to_db([item], session_id="session2", db_path=tmp_db)

        db = get_session(engine)
        second = db.execute(
            text("SELECT last_seen_at FROM products WHERE product_id = 'A000001'")
        ).scalar()
        db.close()

        assert second >= first

    def test_fk_integrity(self, tmp_db):
        """ranking_snapshots.product_id가 products.id를 참조"""
        item = _make_item(product_id="A000001")
        save_to_db([item], session_id="session1", db_path=tmp_db)

        engine = get_engine(tmp_db)
        db = get_session(engine)
        from sqlalchemy import text
        row = db.execute(
            text(
                "SELECT rs.product_id, p.id FROM ranking_snapshots rs "
                "JOIN products p ON rs.product_id = p.id"
            )
        ).fetchone()
        db.close()

        assert row is not None
        assert row[0] == row[1]

    def test_multiple_platforms(self, tmp_db):
        """올리브영 + 무신사 동시 저장"""
        items = [
            _make_item(platform="oliveyoung", product_id="OY001", rank=1),
            _make_item(platform="musinsa", product_id="MS001", rank=1),
        ]
        saved = save_to_db(items, session_id="session1", db_path=tmp_db)
        assert saved == 2

        engine = get_engine(tmp_db)
        db = get_session(engine)
        from sqlalchemy import text
        products = db.execute(text("SELECT COUNT(*) FROM products")).scalar()
        db.close()
        assert products == 2
