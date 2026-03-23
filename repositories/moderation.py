import time
from dataclasses import dataclass
from typing import Mapping, Any, Optional
from hse_backend.clients.postgres import get_pg_connection
from hse_backend.metrics import DB_QUERY_DURATION


class ModerationResultNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ModerationResultStorage:
    async def create_pending(self, item_id: int) -> Mapping[str, Any]:
        query = """
            INSERT INTO moderation_results (item_id, status)
            VALUES ($1, 'pending')
            RETURNING *
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, item_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(
            query_type="insert", table="moderation_results"
        ).observe(duration)
        return dict(row)

    async def get_by_id(self, task_id: int) -> Mapping[str, Any]:
        query = """
            SELECT * FROM moderation_results WHERE id = $1
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, task_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(
            query_type="select", table="moderation_results"
        ).observe(duration)

        if not row:
            raise ModerationResultNotFoundError()
        return dict(row)

    async def get_pending_by_item_id(self, item_id: int) -> Optional[Mapping[str, Any]]:
        """Get pending moderation record for the given item_id."""
        query = """
            SELECT id FROM moderation_results 
            WHERE item_id = $1 AND status = 'pending'
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, item_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(
            query_type="select", table="moderation_results"
        ).observe(duration)
        return dict(row) if row else None

    async def update_completed(
        self, task_id: int, is_violation: bool, probability: float
    ) -> None:
        """Update moderation result as completed."""
        query = """
            UPDATE moderation_results
            SET status = 'completed',
                is_violation = $1,
                probability = $2,
                processed_at = NOW()
            WHERE id = $3
        """
        start = time.time()
        async with get_pg_connection() as conn:
            await conn.execute(query, is_violation, probability, task_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(
            query_type="update", table="moderation_results"
        ).observe(duration)

    async def update_failed(self, item_id: int, error_message: str) -> None:
        """Update moderation result as failed."""
        query = """
            UPDATE moderation_results
            SET status = 'failed',
                error_message = $1,
                processed_at = NOW()
            WHERE item_id = $2 AND status = 'pending'
        """
        start = time.time()
        async with get_pg_connection() as conn:
            await conn.execute(query, error_message, item_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(
            query_type="update", table="moderation_results"
        ).observe(duration)


@dataclass(frozen=True)
class ModerationRepository:
    storage: ModerationResultStorage = ModerationResultStorage()

    async def create_pending(self, item_id: int) -> dict:
        return await self.storage.create_pending(item_id)

    async def get_by_id(self, task_id: int) -> dict:
        return await self.storage.get_by_id(task_id)

    async def get_pending_by_item_id(self, item_id: int) -> Optional[dict]:
        result = await self.storage.get_pending_by_item_id(item_id)
        return result

    async def update_completed(
        self, task_id: int, is_violation: bool, probability: float
    ) -> None:
        await self.storage.update_completed(task_id, is_violation, probability)

    async def update_failed(self, item_id: int, error_message: str) -> None:
        await self.storage.update_failed(item_id, error_message)
