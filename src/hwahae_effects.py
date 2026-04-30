"""화해 AI 분석(효능 점수) enrich.

products 테이블의 화해 제품에 대해 /v14/products/{pid}/effects API 호출 →
effects + product_effects + effect_evidences 테이블 적재.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

API = "https://gateway.hwahae.co.kr/v14/products/{pid}/effects"
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
            log.warning(f"effect fetch failed pid={pid}: {e}")
            return pid, None


def _upsert_effect(db: Session, eff: dict[str, Any]) -> int | None:
    eid = eff.get("id")
    if eid is None:
        return None
    db.execute(text("""
        INSERT INTO effects (id, name) VALUES (:id, :name)
        ON CONFLICT(id) DO UPDATE SET name=excluded.name
    """), {"id": eid, "name": eff.get("name", "")})
    return eid


async def enrich_effects(db: Session) -> dict:
    """화해 제품 중 product_effects 미적재인 것만 enrich."""
    rows = db.execute(text("""
        SELECT p.id, p.product_id
        FROM products p
        LEFT JOIN product_effects pe ON pe.product_id = p.id
        WHERE p.platform='hwahae' AND pe.product_id IS NULL
    """)).fetchall()
    log.info(f"AI 효능 enrich 시작: 화해 신규 제품 {len(rows)}개")

    sem = asyncio.Semaphore(CONCURRENCY)
    enriched = 0
    failed = 0
    total_eff = 0
    now = datetime.now().isoformat()

    async with aiohttp.ClientSession() as http:
        coros = [_fetch(http, str(pid), sem) for _, pid in rows]
        for i, fut in enumerate(asyncio.as_completed(coros), 1):
            pid_str, effects = await fut
            row = db.execute(
                text("SELECT id FROM products WHERE platform='hwahae' AND product_id=:p"),
                {"p": pid_str},
            ).fetchone()
            if row is None or effects is None:
                failed += 1
                continue
            internal_pid = row[0]
            db.execute(text("DELETE FROM product_effects WHERE product_id=:p"), {"p": internal_pid})
            db.execute(text("DELETE FROM effect_evidences WHERE product_id=:p"), {"p": internal_pid})
            for eff in effects:
                eid = _upsert_effect(db, eff)
                if eid is None:
                    continue
                db.execute(text("""
                    INSERT INTO product_effects (product_id, effect_id, score, is_analyzing, collected_at)
                    VALUES (:p, :e, :s, :a, :t)
                """), {
                    "p": internal_pid, "e": eid,
                    "s": int(eff.get("score") or 0),
                    "a": bool(eff.get("is_analyzing")),
                    "t": now,
                })
                for ev in eff.get("evidences") or []:
                    etype = ev.get("type")
                    rtext = ev.get("result")
                    if not etype or not rtext:
                        continue
                    db.execute(text("""
                        INSERT INTO effect_evidences (product_id, effect_id, evidence_type, result_text)
                        VALUES (:p, :e, :t, :r)
                    """), {"p": internal_pid, "e": eid, "t": etype, "r": rtext})
                total_eff += 1
            enriched += 1
            if i % 200 == 0:
                db.commit()
                log.info(f"  진행 {i}/{len(rows)}")

    db.commit()
    log.info(f"AI 효능 enrich 완료: {enriched}/{len(rows)}건 성공, 실패 {failed}, 총 효능 {total_eff}")
    return {"enriched": enriched, "failed": failed, "effects": total_eff}
