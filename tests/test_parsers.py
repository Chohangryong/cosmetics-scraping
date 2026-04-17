from src.parsers import (
    parse_price,
    parse_rank_from_data_attr,
    extract_musinsa_product_name,
)


class TestParsePrice:
    def test_normal(self):
        assert parse_price("21,900") == 21900

    def test_with_won(self):
        assert parse_price("43,000원") == 43000

    def test_zero(self):
        assert parse_price("0") == 0

    def test_none(self):
        assert parse_price(None) is None

    def test_empty(self):
        assert parse_price("") is None

    def test_non_numeric(self):
        assert parse_price("무료") is None

    def test_no_comma(self):
        assert parse_price("9900") == 9900



class TestParseRankFromDataAttr:
    def test_normal(self):
        assert parse_rank_from_data_attr("랭킹^판매랭킹리스트_스킨케어^[상품명]^1") == 1

    def test_rank_50(self):
        assert parse_rank_from_data_attr("랭킹^판매랭킹리스트_스킨케어^[상품명]^50") == 50

    def test_empty(self):
        assert parse_rank_from_data_attr("") == 0

    def test_invalid(self):
        assert parse_rank_from_data_attr("잘못된형식") == 0


class FakeCard:
    """extract_musinsa_product_name 테스트용 가짜 카드 요소"""
    def __init__(self, text: str, brand: str = ""):
        self.text = text
        self.attrib = {"data-item-brand": brand}


class TestExtractMusinsaProductName:
    def test_brand_next_line(self):
        card = FakeCard("순위\nathanbe\n에센스 토너 200ml\n49,140원", brand="athanbe")
        assert extract_musinsa_product_name(card) == "에센스 토너 200ml"

    def test_no_brand_fallback(self):
        card = FakeCard("1\n2\n3\n상품명입니다\n가격", brand="")
        assert extract_musinsa_product_name(card) == "상품명입니다"

    def test_empty_text(self):
        card = FakeCard("", brand="brand")
        assert extract_musinsa_product_name(card) == ""

    def test_short_lines_no_brand(self):
        card = FakeCard("한줄만", brand="없는브랜드")
        assert extract_musinsa_product_name(card) == ""
