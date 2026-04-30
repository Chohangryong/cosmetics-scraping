import asyncio
import json
import logging
import sys
from datetime import datetime

from src.config import parse_args, MUSINSA_CATEGORY_CODES
from src.enricher import enrich_ratings
from src import musinsa_fetcher, hwahae_fetcher
from src.hwahae_ingredients import enrich_ingredients
from src.models import get_engine, get_session
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

    log.info(f"수집 시작 (session: {timestamp}, platforms: {args.platforms}, headless: {args.headless})")

    # 1. 올리브영 (Spider)
    oy_items: list = []
    spider_result = None
    if "oliveyoung" in args.platforms:
        spider = BeautyRankingSpider(
            headless=args.headless,
            crawldir="data/crawl_state",
        )
        spider_result = spider.start(use_uvloop=True)
        oy_items = list(spider_result.items)

    # 2. 무신사 (standalone fetcher)
    ms_items: list = []
    if "musinsa" in args.platforms:
        log.info("무신사 수집 시작")
        ms_items = asyncio.run(musinsa_fetcher.fetch_all(MUSINSA_CATEGORY_CODES))
        log.info(f"무신사 수집 완료: {len(ms_items)}건")

    # 2b. 화해 (gateway API)
    hw_items: list = []
    if "hwahae" in args.platforms:
        log.info(f"화해 수집 시작 (scope={args.hwahae_scope})")
        try:
            leaves = hwahae_fetcher.load_leaves(scope=args.hwahae_scope)
            hw_items = asyncio.run(hwahae_fetcher.fetch_all(leaves))
            log.info(f"화해 수집 완료: {len(hw_items)}건 ({len(leaves)} leaves)")
        except FileNotFoundError as e:
            log.warning(f"화해 건너뜀: {e}")

    all_items = oy_items + ms_items + hw_items

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

    # 5b. 화해 성분 enrich
    if args.enrich_ingredients and "hwahae" in args.platforms:
        db = get_session(get_engine())
        try:
            asyncio.run(enrich_ingredients(db))
        finally:
            db.close()

    # 6. 부분 실패 감지
    counts = {"oliveyoung": len(oy_items), "musinsa": len(ms_items), "hwahae": len(hw_items)}
    if len(all_items) == 0:
        log.error("전체 수집 실패: 0건. 사이트 변경 또는 차단 가능성")
    else:
        zero = [p for p in args.platforms if counts[p] == 0]
        if zero:
            log.warning(f"부분 실패: {zero} 0건 (counts={counts})")

    # 7. 통계
    log.info(f"총 수집: {len(all_items)}건 (counts={counts})")
    log.info(f"DB 저장: {saved}건")
    if spider_result is not None:
        log.info(f"통계: {spider_result.stats}")


if __name__ == "__main__":
    main()
