import re


def parse_price(text: str | None) -> int | None:
    """'21,900' → 21900, '43,000원' → 43000"""
    if not text:
        return None
    clean = text.replace(",", "").replace("원", "").strip()
    return int(clean) if clean.isdigit() else None


def parse_rating_detail(text: str | None) -> float | None:
    """'4.8' 또는 '평점4.8' → 4.8  (상세 페이지, 5점 만점)"""
    if not text:
        return None
    match = re.search(r"([\d.]+)", text.strip())
    if match:
        val = float(match.group(1))
        return val if 0 < val <= 5 else None
    return None


def parse_review_count(text: str | None) -> int | None:
    """'31,649' 또는 '리뷰 31,649건' → 31649"""
    if not text:
        return None
    match = re.search(r"([\d,]+)", text)
    return int(match.group(1).replace(",", "")) if match else None


def calc_discount_rate(original_price: int | None, sale_price: int | None) -> int | None:
    """(43000, 21900) → 49"""
    if not original_price or not sale_price or original_price <= 0:
        return None
    if sale_price >= original_price:
        return 0
    return round((original_price - sale_price) / original_price * 100)


def parse_rank_from_data_attr(data_attr: str) -> int:
    """'랭킹^판매랭킹리스트_스킨케어^[상품명]^1' → 1"""
    try:
        return int(data_attr.split("^")[-1])
    except (ValueError, IndexError):
        return 0


def extract_badges(item) -> str:
    """올리브영 뱃지 목록 추출 (세일/쿠폰/증정/오늘드림)"""
    flags = item.css(".icon_flag")
    return ",".join(f.text.strip() for f in flags if f.text) if flags else ""


def extract_musinsa_product_name(card) -> str:
    """무신사 innerText에서 브랜드 다음 줄이 상품명"""
    lines = [line.strip() for line in (card.text or "").split("\n") if line.strip()]
    brand = card.attrib.get("data-item-brand", "")
    for i, line in enumerate(lines):
        if brand and brand.lower() in line.lower() and i + 1 < len(lines):
            return lines[i + 1]
    return lines[3] if len(lines) > 3 else ""
