import asyncio
import json
import logging
import sys
from datetime import datetime

from src.config import parse_args, MUSINSA_CATEGORY_CODES
from src.enricher import enrich_ratings
from src import musinsa_fetcher
from src.spider import BeautyRankingSpider
from src.storage import save_to_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/crawl.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def main():
    args = parse_args()

    # session_id: JSONL 파일명과 동일한 timestamp (eng review #1)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    log.info(f"수집 시작 (session: {timestamp}, headless: {args.headless})")

    # 1. 올리브영 (Spider)
    spider = BeautyRankingSpider(
        headless=args.headless,
        crawldir="data/crawl_state",
    )
    spider_result = spider.start(use_uvloop=True)
    oy_items = list(spider_result.items)

    # 2. 무신사 (standalone fetcher)
    log.info("무신사 수집 시작")
    ms_items = asyncio.run(musinsa_fetcher.fetch_all(MUSINSA_CATEGORY_CODES))
    log.info(f"무신사 수집 완료: {len(ms_items)}건")

    all_items = oy_items + ms_items

    # 3. JSONL 백업
    jsonl_path = f"data/ranking_{timestamp}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in all_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    log.info(f"JSONL 저장: {jsonl_path}")

    # 4. DB 저장
    saved = save_to_db(all_items, session_id=timestamp)

    # 5. Rating 보강 (올리브영만)
    oy_ids = [i["product_id"] for i in oy_items]
    if oy_ids:
        log.info(f"Rating 보강 시작: 올리브영 {len(oy_ids)}개 상품")
        enriched = asyncio.run(
            enrich_ratings(oy_ids, session_id=timestamp, headless=args.headless)
        )
        log.info(f"Rating 보강: {enriched}건")

    # 6. 부분 실패 감지
    oy_count = len(oy_items)
    ms_count = len(ms_items)

    if len(all_items) == 0:
        log.error("전체 수집 실패: 0건. 사이트 변경 또는 차단 가능성")
    elif oy_count == 0 or ms_count == 0:
        log.warning(f"부분 실패: 올리브영={oy_count}건, 무신사={ms_count}건")

    # 7. 통계
    log.info(f"총 수집: {len(all_items)}건 (올리브영: {oy_count}, 무신사: {ms_count})")
    log.info(f"DB 저장: {saved}건")
    log.info(f"통계: {spider_result.stats}")


if __name__ == "__main__":
    main()
