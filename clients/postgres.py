import asyncio
import asyncpg
from typing import AsyncGenerator, Dict
from contextlib import asynccontextmanager

_pools: Dict[int, asyncpg.Pool] = {}


async def init_pool() -> asyncpg.Pool:
    """Инициализировать пул соединений для текущего event loop. Если пул уже существует, вернуть его."""
    loop = asyncio.get_running_loop()
    if id(loop) in _pools:
        return _pools[id(loop)]

    pool = await asyncpg.create_pool(
        user="postgres",
        password="postgres",
        database="service",
        host="localhost",
        port=5435,
        min_size=1,
        max_size=10,
    )
    _pools[id(loop)] = pool
    return pool


async def close_pool() -> None:
    """Закрывает пул соединения."""
    pools_to_close = list(_pools.values())
    _pools.clear()

    for pool in pools_to_close:
        try:
            await asyncio.wait_for(pool.close(), timeout=5.0)
        except asyncio.TimeoutError:
            # Принудительно закрыть пул, если он не отвечает
            pool.terminate()
        except RuntimeError as e:
            if "Event loop is closed" in str(
                e
            ) or "attached to a different loop" in str(e):
                # Если событие loop уже закрыт или пул прикреплен к другому loop, попытаться принудительно закрыть
                pool.terminate()
            else:
                raise
        except Exception:
            try:
                pool.terminate()
            except Exception:
                pass


def get_pool() -> asyncpg.Pool:
    loop = asyncio.get_running_loop()
    pool = _pools.get(id(loop))
    if pool is None:
        raise RuntimeError(
            "Connection pool not initialized for this event loop. Call init_pool() first."
        )
    return pool


@asynccontextmanager
async def get_pg_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    loop = asyncio.get_running_loop()
    pool = _pools.get(id(loop))
    if pool is None:
        pool = await init_pool()

    connection: asyncpg.Connection = await pool.acquire()
    try:
        yield connection
    finally:
        await pool.release(connection)
