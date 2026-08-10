"""Postgres-backed feedback storage for draft replies."""

from __future__ import annotations

import os
from typing import Any

import asyncpg

_POOL: asyncpg.Pool | None = None

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    draft TEXT NOT NULL,
    source_ids TEXT[] NOT NULL,
    rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in the environment.")
    return database_url


async def get_pool() -> asyncpg.Pool:
    global _POOL
    if _POOL is None:
        _POOL = await asyncpg.create_pool(
            dsn=_get_database_url(),
            min_size=1,
            max_size=5,
        )
    return _POOL


async def init_feedback_table() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_TABLE_SQL)


async def submit_feedback(question: str, draft: str, source_ids: list[str], rating: str) -> None:
    if rating not in {"up", "down"}:
        raise ValueError("rating must be 'up' or 'down'")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feedback (question, draft, source_ids, rating)
            VALUES ($1, $2, $3, $4)
            """,
            question,
            draft,
            source_ids,
            rating,
        )


async def get_feedback_summary() -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int AS total_count,
                COUNT(*) FILTER (WHERE rating = 'up')::int AS up_count,
                COUNT(*) FILTER (WHERE rating = 'down')::int AS down_count
            FROM feedback
            """
        )

    total_count = int(row["total_count"] or 0) if row else 0
    up_count = int(row["up_count"] or 0) if row else 0
    down_count = int(row["down_count"] or 0) if row else 0
    ratio = (up_count / down_count) if down_count else None

    return {
        "total_count": total_count,
        "up_count": up_count,
        "down_count": down_count,
        "up_down_ratio": ratio,
    }
