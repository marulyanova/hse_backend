from typing import Optional
from clients.postgres import get_pg_connection


class UserRepository:
    async def create_user(self, user_id: int, is_verified: bool = False) -> dict:

        # валидация user_id, должно быть положительным целым числом
        if not isinstance(user_id, int):
            raise TypeError("user_id must be an integer")
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        query = """
            INSERT INTO users (id, is_verified)
            VALUES ($1, $2)
            ON CONFLICT (id) DO NOTHING
            RETURNING id, is_verified;
        """
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, user_id, is_verified)
            if row:
                return dict(row)
            existing = await self.get_user_by_id(user_id)
            return existing

    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        query = "SELECT id, is_verified FROM users WHERE id = $1;"
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, user_id)
            return dict(row) if row else None
