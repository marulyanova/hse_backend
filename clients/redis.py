import os
import json
from typing import Optional, Any, Dict
from redis.asyncio import Redis, ConnectionPool


class RedisClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        decode_responses: bool = True,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.decode_responses = decode_responses
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
        self._connected = False

    async def connect(self):
        if self._connected and self._client is not None:
            return

        try:
            self._pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=self.decode_responses,
                max_connections=10,
            )
            self._client = Redis(connection_pool=self._pool)
            await self._client.ping()
            self._connected = True
        except Exception as e:
            self._connected = False
            raise

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
            self._connected = False
            if self._pool:
                await self._pool.disconnect()
                self._pool = None

    async def get(self, key: str) -> Optional[Any]:

        # получение кэша по ключу
        if not self._connected:
            try:
                await self.connect()
            except Exception:
                return None

        if self._client is None:
            return None

        try:
            value = await self._client.get(key)
            return value
        except Exception as e:
            return None

    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> bool:

        # сохранение кэша по ключу с TTL
        if not self._connected:
            try:
                await self.connect()
            except Exception as e:
                return False

        if self._client is None:
            return False

        try:
            serialized = json.dumps(value)
            await self._client.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            return False

    async def delete(self, key: str) -> bool:
        if not self._connected:
            try:
                await self.connect()
            except Exception:
                return False

        if self._client is None:
            return False

        try:
            result = await self._client.delete(key)
            return result > 0
        except Exception as e:
            return False

    async def exists(self, key: str) -> bool:
        if not self._connected:
            try:
                await self.connect()
            except Exception:
                return False

        if self._client is None:
            return False

        try:
            return bool(await self._client.exists(key))
        except Exception as e:
            return False


redis_client = RedisClient(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
)
