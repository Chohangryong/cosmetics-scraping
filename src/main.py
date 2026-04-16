import logging
import sys
from datetime import datetime

from src.config import parse_args
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

    spider = BeautyRankingSpider(
        headless=args.headless,
        crawldir="data/crawl_state",
    )
    result = spider.start(use_uvloop=True)

    # 1. JSONL 백업
    jsonl_path = f"data/ranking_{timestamp}.jsonl"
    result.items.to_jsonl(jsonl_path)
    log.info(f"JSONL 저장: {jsonl_path}")

    # 2. DB 저장
    saved = save_to_db(result.items, session_id=timestamp)

    # 3. 부분 실패 감지 (eng review: 개선 3)
    oy_count = sum(1 for i in result.items if i.get("platform") == "oliveyoung")
    ms_count = sum(1 for i in result.items if i.get("platform") == "musinsa")

    if len(result.items) == 0:
        log.error("전체 수집 실패: 0건. 사이트 변경 또는 차단 가능성")
    elif oy_count == 0 or ms_count == 0:
        log.warning(f"부분 실패: 올리브영={oy_count}건, 무신사={ms_count}건")

    # 4. 통계
    log.info(f"총 수집: {len(result.items)}건 (올리브영: {oy_count}, 무신사: {ms_count})")
    log.info(f"DB 저장: {saved}건")
    log.info(f"통계: {result.stats}")


if __name__ == "__main__":
    main()
