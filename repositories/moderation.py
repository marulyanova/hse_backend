from dataclasses import dataclass
from typing import Mapping, Any
from clients.postgres import get_pg_connection


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
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, item_id)
            return dict(row)

    async def get_by_id(self, task_id: int) -> Mapping[str, Any]:
        query = """
            SELECT * FROM moderation_results WHERE id = $1
        """
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, task_id)
            if not row:
                raise ModerationResultNotFoundError()
            return dict(row)


@dataclass(frozen=True)
class ModerationRepository:
    storage: ModerationResultStorage = ModerationResultStorage()

    async def create_pending(self, item_id: int) -> dict:
        return await self.storage.create_pending(item_id)

    async def get_by_id(self, task_id: int) -> dict:
        return await self.storage.get_by_id(task_id)
