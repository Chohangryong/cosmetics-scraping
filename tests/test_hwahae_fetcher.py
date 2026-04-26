from src.hwahae_fetcher import parse_item


SAMPLE = {
    "brand": {"id": 204, "name": "리더스"},
    "goods": {
        "id": 70021,
        "product_id": 2137037,
        "price": 23000,
        "discount_rate": 8,
        "discount_price": None,
        "name": "그린 콜라겐 와이드 핏 아이패치 60매",
    },
    "is_rank_new": False,
    "rank_delta": 0,
    "product": {
        "id": 2137037,
        "name": "그린 콜라겐 와이드 핏 아이패치",
        "review_count": 82,
        "review_rating": 4.61,
        "is_commerce": True,
        "price": 25000,
    },
}


def test_parse_item_basic_fields():
    out = parse_item(SAMPLE, category="스킨케어", page=1, idx_in_page=0)
    assert out["platform"] == "hwahae"
    assert out["category"] == "스킨케어"
    assert out["product_id"] == "2137037"
    assert out["brand"] == "리더스"
    assert out["name"] == "그린 콜라겐 와이드 핏 아이패치"
    assert out["rank"] == 1
    assert out["original_price"] == 23000
    assert out["sale_price"] == 23000  # discount_price=None → fallback to price
    assert out["discount_rate"] == 8
    assert out["review_count"] == 82
    assert out["rating"] == 4.61
    assert out["review_score"] == 92  # 4.61 * 20 = 92.2 → 92
    assert out["badge"] == ""


def test_parse_item_rank_calc():
    out = parse_item(SAMPLE, category="스킨케어", page=3, idx_in_page=5)
    assert out["rank"] == 2 * 20 + 5 + 1  # 46


def test_parse_item_new_badge():
    sample = {**SAMPLE, "is_rank_new": True}
    out = parse_item(sample, category="x", page=1, idx_in_page=0)
    assert out["badge"] == "NEW"


def test_parse_item_missing_rating():
    sample = {**SAMPLE, "product": {**SAMPLE["product"], "review_rating": None}}
    out = parse_item(sample, category="x", page=1, idx_in_page=0)
    assert out["rating"] is None
    assert out["review_score"] is None
