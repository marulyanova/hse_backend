import asyncio
import asyncpg
from typing import AsyncGenerator, Dict
from contextlib import asynccontextmanager

_pools: Dict[int, asyncpg.Pool] = {}


async def init_pool() -> asyncpg.Pool:
    """Initialize the connection pool for the current event loop."""
    loop = asyncio.get_running_loop()
    if id(loop) in _pools:
        return _pools[id(loop)]

    pool = await asyncpg.create_pool(
        user="postgres",
        password="postgres",
        database="service",
        host="localhost",
        port=5435,
        min_size=5,
        max_size=20,
    )
    _pools[id(loop)] = pool
    return pool


async def close_pool() -> None:
    """Close the connection pool for the current event loop."""
    loop = asyncio.get_running_loop()
    pool = _pools.pop(id(loop), None)
    if pool is not None:
        await pool.close()


def get_pool() -> asyncpg.Pool:
    """Get the connection pool associated with the current event loop."""
    loop = asyncio.get_running_loop()
    pool = _pools.get(id(loop))
    if pool is None:
        raise RuntimeError(
            "Connection pool not initialized for this event loop. Call init_pool() first."
        )
    return pool


@asynccontextmanager
async def get_pg_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a connection from the pool."""
    loop = asyncio.get_running_loop()
    pool = _pools.get(id(loop))
    if pool is None:
        pool = await init_pool()

    connection: asyncpg.Connection = await pool.acquire()
    try:
        yield connection
    finally:
        await pool.release(connection)
