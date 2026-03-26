import time
import json
from typing import Optional, Dict, Any
from hse_backend.clients.postgres import get_pg_connection
from hse_backend.clients.redis import redis_client
from hse_backend.metrics import DB_QUERY_DURATION
from hse_backend.services.auth import AuthService


class AccountRepository:

    async def create_account(
        self, login: str, password: str, is_blocked: bool = False
    ) -> Dict[str, Any]:
        if not login or not isinstance(login, str):
            raise ValueError("login must be a non-empty string")
        if not password or not isinstance(password, str):
            raise ValueError("password must be a non-empty string")

        # хэшировать пароль перед сохранением
        hashed_password = AuthService.hash_password(password)

        query = """
            INSERT INTO account (login, password, is_blocked)
            VALUES ($1, $2, $3)
            RETURNING id, login, password, is_blocked;
        """
        start = time.time()
        async with get_pg_connection() as conn:
            row = await conn.fetchrow(query, login, hashed_password, is_blocked)
        duration = time.time() - start
        DB_QUERY_DURATION.labels(query_type="insert", table="account").observe(duration)

        if not row:
            raise RuntimeError("Failed to create account")
        return dict(row)

    async def get_account_by_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        if not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id must be a positive integer")

        # пытаться получить из кэша Redis
        cache_key = f"account:{account_id}"

        try:
            cached_account = await redis_client.get(cache_key)
            if cached_account:
                return (
                    json.loads(cached_account)
                    if isinstance(cached_account, str)
                    else cached_account
                )
        except Exception as e:
            print(f"Redis cache get error: {e}")

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

        if not row:
            return None

        account_dict = dict(row)

        # кэшировать результат в Redis на 5 минут
        try:
            await redis_client.set(cache_key, account_dict, ttl_seconds=300)
        except Exception as e:
            print(f"Redis cache set error: {e}")

        return account_dict

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

        if row:
            # Инвалидировать кэш Redis при удалении аккаунта
            cache_key = f"account:{account_id}"
            try:
                await redis_client.delete(cache_key)
            except Exception as e:
                print(f"Redis cache delete error: {e}")

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

        # инвалидировать кэш Redis при изменении статуса блокировки
        cache_key = f"account:{account_id}"
        try:
            await redis_client.delete(cache_key)
        except Exception as e:
            print(f"Redis cache delete error: {e}")

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

        # Инвалидировать кэш Redis при изменении статуса блокировки
        cache_key = f"account:{account_id}"
        try:
            await redis_client.delete(cache_key)
        except Exception as e:
            print(f"Redis cache delete error: {e}")

        return row is not None
