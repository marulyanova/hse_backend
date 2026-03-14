import time
from typing import Optional, Dict, Any
from clients.postgres import get_pg_connection

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from metrics import DB_QUERY_DURATION


class AccountRepository:

    async def create_account(
        self, login: str, password: str, is_blocked: bool = False
    ) -> Dict[str, Any]:
        if not login or not isinstance(login, str):
            raise ValueError("login must be a non-empty string")
        if not password or not isinstance(password, str):
            raise ValueError("password must be a non-empty string")

        query = """
            INSERT INTO account (login, password, is_blocked)
            VALUES ($1, $2, $3)
            RETURNING id, login, password, is_blocked;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, login, password, is_blocked)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="insert", table="account").observe(duration)

        if not row:
            raise RuntimeError("Failed to create account")
        return dict(row)

    async def get_account_by_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        if not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id must be a positive integer")

        query = """
            SELECT id, login, password, is_blocked
            FROM account
            WHERE id = $1;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, account_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="select", table="account").observe(duration)

        return dict(row) if row else None

    # найти аккаунт по логину
    async def get_account_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        if not login or not isinstance(login, str):
            raise ValueError("login must be a non-empty string")

        query = """
            SELECT id, login, password, is_blocked
            FROM account
            WHERE login = $1;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, login)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="select", table="account").observe(duration)

        return dict(row) if row else None

    async def get_account_by_login_password(
        self, login: str, password: str
    ) -> Optional[Dict[str, Any]]:
        if not login or not isinstance(login, str):
            raise ValueError("login must be a non-empty string")
        if not password or not isinstance(password, str):
            raise ValueError("password must be a non-empty string")

        query = """
            SELECT id, login, password, is_blocked
            FROM account
            WHERE login = $1 AND password = $2 AND is_blocked = false;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, login, password)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="select", table="account").observe(duration)

        return dict(row) if row else None

    # удалить аккаунт
    async def delete_account(self, account_id: int) -> bool:
        if not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id must be a positive integer")

        query = """
            DELETE FROM account
            WHERE id = $1
            RETURNING id;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, account_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="delete", table="account").observe(duration)

        return row is not None

    # заблокировать аккаунт
    async def block_account(self, account_id: int) -> bool:
        if not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id must be a positive integer")

        query = """
            UPDATE account 
            SET is_blocked = TRUE
            WHERE id = $1
            RETURNING id;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, account_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="update", table="account").observe(duration)

        return row is not None

    # разблокировать аккаунт
    async def unblock_account(self, account_id: int) -> bool:
        if not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id must be a positive integer")

        query = """
            UPDATE account 
            SET is_blocked = FALSE
            WHERE id = $1
            RETURNING id;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, account_id)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="update", table="account").observe(duration)

        return row is not None
