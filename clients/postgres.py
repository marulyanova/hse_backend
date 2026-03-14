import asyncpg
from typing import AsyncGenerator
from contextlib import asynccontextmanager


@asynccontextmanager
async def get_pg_connection() -> AsyncGenerator[None, asyncpg.Connection]:

    connection: asyncpg.Connection = await asyncpg.connect(
        user="postgres",
        password="postgres",
        database="service",
        host="localhost",
        port=5435,  # изменено с 5432 на 5435, т.к. сейчас postgres в docker
    )

    yield connection

    await connection.close()
