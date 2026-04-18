import asyncio
import logging

from scrapling.fetchers import StealthyFetcher

from src.parsers import parse_rating_detail, parse_review_count
from src.storage import update_ratings

log = logging.getLogger(__name__)

DETAIL_URL = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={}"


async def _fetch_one(
    fetcher: StealthyFetcher,
    product_id: str,
    session_id: str,
    headless: bool,
    db_path: str,
    delay: float,
    semaphore: asyncio.Semaphore,
    lock: asyncio.Lock,
    counter: list[int],
    total: int,
    stagger: float,
) -> None:
    await asyncio.sleep(stagger)
    async with semaphore:
        url = DETAIL_URL.format(product_id)
        try:
            page = await fetcher.async_fetch(
                url,
                headless=headless,
                network_idle=False,
                disable_resources=False,
                wait_selector="span.rating",
                wait_selector_state="visible",
            )
        except Exception as e:
            log.warning(f"rating wait_selector 타임아웃, 재시도 ({product_id}): {e}")
            try:
                page = await fetcher.async_fetch(
                    url,
                    headless=headless,
                    network_idle=False,
                    disable_resources=False,
                )
            except Exception as e2:
                log.warning(f"rating 보강 실패 ({product_id}): {e2}")
                await asyncio.sleep(delay)
                return

        try:
            rating = parse_rating_detail(page.css("span.rating::text").get())
            review_count = parse_review_count(
                page.css('[class*="GoodsDetailTabs_review-count"]::text').get()
            )
            update_ratings(product_id, session_id, rating, review_count, db_path)
            async with lock:
                counter[0] += 1
                done = counter[0]
            if rating is None:
                log.info(f"rating 없는 상품 (미출시 등) ({product_id})")
            else:
                log.debug(f"보강 ({done}/{total}): {product_id} → ★{rating} 리뷰{review_count}건")
        except Exception as e:
            log.warning(f"rating 파싱 실패 ({product_id}): {e}")

        await asyncio.sleep(delay)


async def enrich_ratings(
    product_ids: list[str],
    session_id: str,
    headless: bool = False,
    db_path: str = "data/beauty_ranking.db",
    delay: float = 7.0,
    concurrency: int = 5,
    stagger_interval: float = 0.5,
) -> int:
    """올리브영 상품 상세 페이지에서 rating + review_count 병렬 수집 후 DB 업데이트.

    concurrency개 동시 실행, stagger_interval 간격으로 순차 시작.
    """
    fetcher = StealthyFetcher(auto_match=False)
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    counter = [0]
    total = len(product_ids)

    tasks = [
        _fetch_one(
            fetcher, pid, session_id, headless, db_path, delay,
            semaphore, lock, counter, total,
            stagger=i * stagger_interval,
        )
        for i, pid in enumerate(product_ids)
    ]
    await asyncio.gather(*tasks)

    enriched = counter[0]
    log.info(f"Rating 보강 완료: {enriched}/{total}건")
    return enriched
