import time
from typing import Optional, Dict, Any
from clients.postgres import get_pg_connection

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from metrics import DB_QUERY_DURATION


class AdRepository:
    async def create_ad(
        self,
        seller_id: int,
        item_id: int,
        name: str,
        description: str,
        category: int,
        images_qty: int,
    ) -> Dict[str, Any]:
        if not isinstance(item_id, int):
            raise TypeError("item_id must be an integer")
        if item_id <= 0:
            raise ValueError("item_id must be a positive integer")

        query = """
            INSERT INTO ads (seller_id, item_id, name, description, category, images_qty)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING item_id, seller_id, name, description, category, images_qty;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(
                query, seller_id, item_id, name, description, category, images_qty
            )
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="insert", table="ads").observe(duration)

        if not row:
            raise RuntimeError("Failed to create ad")
        return dict(row)

    async def get_ad_with_seller(self, item_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT 
                a.item_id, a.seller_id, u.is_verified AS is_verified_seller,
                a.name, a.description, a.category, a.images_qty
            FROM ads a
            JOIN users u ON a.seller_id = u.id
            WHERE a.item_id = $1;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, item_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="select", table="ads").observe(duration)

        return dict(row) if row else None

    async def close_ad(self, item_id: int) -> bool:
        if not isinstance(item_id, int):
            raise TypeError("item_id must be an integer")
        if item_id <= 0:
            raise ValueError("item_id must be a positive integer")

        query = """
            UPDATE ads SET is_closed = TRUE
            WHERE item_id = $1
            RETURNING item_id;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, item_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="update", table="ads").observe(duration)

        return row is not None
