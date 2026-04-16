import re


def parse_price(text: str | None) -> int | None:
    """'21,900' → 21900, '43,000원' → 43000"""
    if not text:
        return None
    clean = text.replace(",", "").replace("원", "").strip()
    return int(clean) if clean.isdigit() else None


def parse_rating(text: str | None) -> float | None:
    """'10점만점에 5.5점' → 5.5"""
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)점$", text)
    return float(match.group(1)) if match else None


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
