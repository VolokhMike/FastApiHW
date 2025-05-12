import asyncio
import json
import os
from typing import Any

import aiohttp
import aiomysql
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

MYSQL_CONNECTION_DATA: dict[str, Any] = {
    "host": os.environ.get("MYSQL_HOST"),
    "port": int(os.environ.get("MYSQL_PORT", default=3306)),
    "user": os.environ.get("MYSQL_USER"),
    "password": os.environ.get("MYSQL_PASSWORD"),
    "db": os.environ.get("MYSQL_DB"),
}

@asynccontextmanager
async def create_tables(_: FastAPI):
    async with aiomysql.connect(**MYSQL_CONNECTION_DATA) as connection:
        cursor: aiomysql.Cursor = await connection.cursor()
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT,
                name VARCHAR(50),
                email VARCHAR(20),
                PRIMARY KEY(id)
            );
            """
        )
        await connection.commit()
    yield


app = FastAPI(title="TODO", lifespan=create_tables)


class UserNotFoundError(Exception):
    """Помилка виникає, коли користувача не існує."""

async def fetch_users() -> Any:

    url = "https://jsonplaceholder.typicode.com/users"
    async with aiohttp.ClientSession() as session:
        async with session.get(url=url) as response:
            return await response.json()


async def get_mysql_pool() -> aiomysql.Pool:
    return await aiomysql.create_pool(**MYSQL_CONNECTION_DATA)


@app.post("/users/")
async def add_user(name: str, email: str ) -> dict[str, str]:
    pool = await get_mysql_pool()

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO users (name, email) VALUES (%s, %s);", (name, email)
                )

                if email is not None:
                    raise HTTPException("User is not found")
            await conn.commit()

    except aiomysql.Error as e:
        raise e
    finally:
        pool.close()
        await pool.wait_closed()

    return {"message": f"User {name} with email {email} has been added"}

@app.delete("/users/")
async def delete_user(email: str) -> dict[str, str]:
    pool = await get_mysql_pool()

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1 FROM users WHERE email=%s;", (email,))
                user = await cursor.fetchone()

                if user is None:
                    raise HTTPException("User is not found")
                
                await cursor.execute("DELETE FROM users WHERE email=%s;", (email,))
                await conn.commit()

    except aiomysql.Error as e:
        raise e
    finally:
        pool.close()
        await pool.wait_closed()
    return {"message": f"User with email {email} has been deleted"}

@app.get("/users/")
async def get_users() -> Any:
    pool = await get_mysql_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT * FROM users;")
                users: Any = await cursor.fetchall()
    except aiomysql.Error as e:
        raise e
    finally:
        pool.close()
        await pool.wait_closed()

    return users


async def main() -> None:
    jsonplaceholder_users: Any = await fetch_users()
    print(json.dumps(obj=jsonplaceholder_users, indent=4))

    mysql_users: Any = await get_users()
    print(json.dumps(obj=mysql_users, indent=4))

    adding_result: dict[str, str] = await add_user(name="Mike", email="mikimv09@gmail.com")
    print(adding_result)

    deleting_result: dict[str, str] = await delete_user(email="mikimv09@gmail.com")
    print(deleting_result)






