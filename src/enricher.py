import asyncio
import logging

from scrapling.fetchers import StealthyFetcher

from src.parsers import parse_rating_detail, parse_review_count
from src.storage import update_ratings

log = logging.getLogger(__name__)

DETAIL_URL = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={}"


async def enrich_ratings(
    product_ids: list[str],
    session_id: str,
    headless: bool = False,
    db_path: str = "data/beauty_ranking.db",
    delay: float = 2.0,
) -> int:
    """올리브영 상품 상세 페이지에서 rating + review_count 수집 후 DB 업데이트.

    순차 실행 (delay 간격). 총 소요: len(product_ids) * delay 초.
    """
    fetcher = StealthyFetcher(auto_match=False)
    enriched = 0

    for i, product_id in enumerate(product_ids):
        url = DETAIL_URL.format(product_id)
        try:
            page = await fetcher.async_fetch(
                url,
                headless=headless,
                network_idle=True,
                disable_resources=False,
            )
            rating = parse_rating_detail(page.css("span.rating::text").get())
            review_count = parse_review_count(
                page.css('[class*="GoodsDetailTabs_review-count"]::text').get()
            )
            update_ratings(product_id, session_id, rating, review_count, db_path)
            log.debug(f"보강 ({i+1}/{len(product_ids)}): {product_id} → ★{rating} 리뷰{review_count}건")
            enriched += 1
        except Exception as e:
            log.warning(f"rating 보강 실패 ({product_id}): {e}")

        await asyncio.sleep(delay)

    log.info(f"Rating 보강 완료: {enriched}/{len(product_ids)}건")
    return enriched
