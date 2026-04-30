"""화해 성분 정보 enrich.

products 테이블의 화해 제품에 대해 /v14/products/{pid}/ingredients API 호출 →
ingredients + product_ingredients 테이블 적재.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

API = "https://gateway.hwahae.co.kr/v14/products/{pid}/ingredients"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Origin": "https://www.hwahae.co.kr",
    "Referer": "https://www.hwahae.co.kr/",
    "authorization": "Bearer",
    "hwahae-device-id": "anonymous",
    "hwahae-user-id": "anonymous",
}
CONCURRENCY = 4
TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _fetch(session: aiohttp.ClientSession, pid: str, sem: asyncio.Semaphore) -> tuple[str, list[dict] | None]:
    async with sem:
        try:
            async with session.get(API.format(pid=pid), headers=HEADERS, timeout=TIMEOUT) as r:
                if r.status != 200:
                    return pid, None
                d = await r.json()
                data = d.get("data")
                return pid, data if isinstance(data, list) else None
        except Exception as e:
            log.warning(f"ingredient fetch failed pid={pid}: {e}")
            return pid, None


def _upsert_ingredient(db: Session, ing: dict[str, Any]) -> int | None:
    iid = ing.get("id")
    if iid is None:
        return None
    db.execute(text("""
        INSERT INTO ingredients (id, name, ewg, is_twenty, is_allergy, formulation_purpose, purpose_groups)
        VALUES (:id, :name, :ewg, :twenty, :allergy, :purpose, :groups)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, ewg=excluded.ewg, is_twenty=excluded.is_twenty,
            is_allergy=excluded.is_allergy, formulation_purpose=excluded.formulation_purpose,
            purpose_groups=excluded.purpose_groups
    """), {
        "id": iid,
        "name": ing.get("representative_name", ""),
        "ewg": ing.get("ewg"),
        "twenty": bool(ing.get("is_twenty")),
        "allergy": bool(ing.get("is_allergy")),
        "purpose": ing.get("formulation_purpose"),
        "groups": json.dumps(ing.get("purpose_group_info") or [], ensure_ascii=False),
    })
    return iid


async def enrich_ingredients(db: Session) -> dict:
    """화해 제품 전체에 대해 성분 enrich. db는 commit까지 책임."""
    rows = db.execute(text("SELECT id, product_id FROM products WHERE platform='hwahae'")).fetchall()
    log.info(f"성분 enrich 시작: 화해 제품 {len(rows)}개")

    sem = asyncio.Semaphore(CONCURRENCY)
    enriched = 0
    failed = 0
    total_ing = 0

    async with aiohttp.ClientSession() as http:
        coros = [_fetch(http, str(pid), sem) for _, pid in rows]
        for i, fut in enumerate(asyncio.as_completed(coros), 1):
            pid_str, ingredients = await fut
            # pid_str로 products.id 역조회
            row = db.execute(text("SELECT id FROM products WHERE platform='hwahae' AND product_id=:p"), {"p": pid_str}).fetchone()
            if row is None or ingredients is None:
                failed += 1
                continue
            internal_pid = row[0]
            # 기존 매핑 삭제 (재실행 시 중복 방지)
            db.execute(text("DELETE FROM product_ingredients WHERE product_id=:p"), {"p": internal_pid})
            for pos, ing in enumerate(ingredients, 1):
                iid = _upsert_ingredient(db, ing)
                if iid is None:
                    continue
                db.execute(text("""
                    INSERT INTO product_ingredients (product_id, ingredient_id, position)
                    VALUES (:p, :i, :pos)
                    ON CONFLICT(product_id, ingredient_id) DO UPDATE SET position=excluded.position
                """), {"p": internal_pid, "i": iid, "pos": pos})
                total_ing += 1
            enriched += 1
            if i % 200 == 0:
                db.commit()
                log.info(f"  진행 {i}/{len(rows)}")

    db.commit()
    log.info(f"성분 enrich 완료: {enriched}/{len(rows)}건 성공, 실패 {failed}, 총 매핑 {total_ing}")
    return {"enriched": enriched, "failed": failed, "mappings": total_ing}
