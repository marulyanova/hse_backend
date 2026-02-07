from typing import Optional, Dict, Any
from clients.postgres import get_pg_connection


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
        # валидация item_id, должно быть положительным целым числом
        if not isinstance(item_id, int):
            raise TypeError("item_id must be an integer")
        if item_id <= 0:
            raise ValueError("item_id must be a positive integer")

        query = """
            INSERT INTO ads (seller_id, item_id, name, description, category, images_qty)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING item_id, seller_id, name, description, category, images_qty;
        """
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(
                query, seller_id, item_id, name, description, category, images_qty
            )
            if not row:
                raise RuntimeError("Failed to create ad")
            return dict(row)

    async def get_ad_with_seller(self, item_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT 
                a.item_id,
                a.seller_id,
                u.is_verified AS is_verified_seller,
                a.name,
                a.description,
                a.category,
                a.images_qty
            FROM ads a
            JOIN users u ON a.seller_id = u.id
            WHERE a.item_id = $1;
        """
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, item_id)
            return dict(row) if row else None
