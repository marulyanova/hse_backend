import time
from typing import Optional
from hse_backend.clients.postgres import get_pg_connection
from hse_backend.metrics import DB_QUERY_DURATION


class UserRepository:
    async def create_user(self, user_id: int, is_verified: bool = False) -> dict:
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
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, user_id, is_verified)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="insert", table="users").observe(duration)

        if row:
            return dict(row)
        existing = await self.get_user_by_id(user_id)
        return existing

    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        query = "SELECT id, is_verified FROM users WHERE id = $1;"
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, user_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="select", table="users").observe(duration)
        return dict(row) if row else None
