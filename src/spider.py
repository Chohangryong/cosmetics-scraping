import asyncio
import logging

from scrapling.spiders import Spider, Request, Response
from scrapling.fetchers import AsyncStealthySession

from src.config import (
    OLIVEYOUNG_URLS,
    MUSINSA_URLS,
    ADAPTIVE_MODE,
    BLOCKED_DOMAINS,
    parse_args,
)
from src.parsers import (
    parse_price,
    parse_rank_from_data_attr,
    calc_discount_rate,
    extract_badges,
)

log = logging.getLogger(__name__)


class BeautyRankingSpider(Spider):
    name = "beauty_ranking"

    start_urls: list[str] = []
    concurrent_requests: int = 1
    download_delay: int = 20
    max_blocked_retries: int = 3
    robots_txt_obey: bool = False

    def __init__(self, headless: bool = False, **kwargs):
        self._headless = headless
        super().__init__(**kwargs)

    # ── Multi-Session 설정 ──
    def configure_sessions(self, manager):
        manager.add(
            "oliveyoung",
            AsyncStealthySession(
                headless=self._headless,
                network_idle=True,
                disable_resources=True,
                blocked_domains=BLOCKED_DOMAINS,
                hide_canvas=True,
                block_webrtc=True,
                timeout=60000,
                google_search=True,
                solve_cloudflare=False,
            ),
            lazy=False,
        )
        manager.add(
            "musinsa",
            AsyncStealthySession(
                headless=self._headless,
                network_idle=True,
                disable_resources=True,
                blocked_domains=BLOCKED_DOMAINS,
                hide_canvas=True,
                block_webrtc=True,
                timeout=60000,
                google_search=True,
                solve_cloudflare=False,
            ),
            lazy=True,
        )

    # ── 시작 요청 ──
    async def start_requests(self):
        for url, category in OLIVEYOUNG_URLS:
            yield Request(
                url=url,
                callback=self.parse_oliveyoung,
                sid="oliveyoung",
                meta={"platform": "oliveyoung", "category": category},
            )
        for url, category in MUSINSA_URLS:
            if "TBD" in url:
                log.info(f"무신사 {category} 건너뜀: categoryCode 미확정")
                continue
            yield Request(
                url=url,
                callback=self.parse_musinsa,
                sid="musinsa",
                meta={"platform": "musinsa", "category": category},
            )

    # ── 올리브영 파싱 (Scrapy-style Selector API) ──
    async def parse_oliveyoung(self, response: Response):
        items = response.css("ul.cate_prd_list > li")

        if not items:
            log.error(f"올리브영 파싱 0건: {response.meta.get('category')}")
            return

        for item in items[:50]:
            product_id = item.css("a[data-ref-goodsno]::attr(data-ref-goodsno)").get("")
            if not product_id:
                continue
            data_attr = item.css("a[data-ref-goodsno]::attr(data-attr)").get("")
            sale_price = parse_price(item.css(".tx_cur .tx_num::text").get())
            original_price = parse_price(item.css(".tx_org .tx_num::text").get())
            yield {
                "platform": "oliveyoung",
                "category": response.meta["category"],
                "product_id": product_id,
                "rank": parse_rank_from_data_attr(data_attr),
                "brand": (item.css(".tx_brand::text").get("")).strip(),
                "name": (item.css(".tx_name::text").get("")).strip(),
                "sale_price": sale_price,
                "original_price": original_price,
                "discount_rate": calc_discount_rate(original_price, sale_price),
                "rating": None,  # 상세 페이지에서 수집 (enrich_ratings)
                "badge": ",".join(item.css(".icon_flag::text").getall()).strip(),
            }

    # ── 무신사 파싱 ──
    async def parse_musinsa(self, response: Response):
        items = response.css('[class*="UIProductColumn__Wrap"][class*="gtm-view-item-list"]')

        if not items:
            log.error(f"무신사 파싱 0건: {response.meta.get('category')}")
            return

        for card in items[:50]:
            product_id = card.css("::attr(data-item-id)").get("")
            if not product_id:
                continue
            name_raw = card.css("img::attr(alt)").get("")
            name = name_raw.replace(" 상품 이미지", "").strip()
            original_price = int(card.css("::attr(data-original-price)").get("0") or "0") or None
            sale_price = int(card.css("::attr(data-price)").get("0") or "0") or None
            discount_rate = int(card.css("::attr(data-discount-rate)").get("0") or "0") or None
            yield {
                "platform": "musinsa",
                "category": response.meta["category"],
                "product_id": product_id,
                "rank": int(card.css("::attr(data-index)").get("0")),
                "brand": card.css("::attr(data-item-brand)").get(""),
                "name": name,
                "original_price": original_price,
                "sale_price": sale_price,
                "discount_rate": discount_rate,
                "badge": card.css("::attr(data-item-flag)").get(""),
                "rating": None,
            }

        # 무신사 Crawl-delay: 60 준수 (download_delay 20 + sleep 40 = 60초)
        await asyncio.sleep(40)

    # ── 기본 parse (Spider 추상 메서드 구현) ──
    async def parse(self, response: Response):
        pass

    # ── 차단 감지 ──
    async def is_blocked(self, response: Response) -> bool:
        if response.status and response.status >= 400:
            return True
        body = response.text or ""
        if "정상 동작하지 않습니다" in body:
            return True
        return False
