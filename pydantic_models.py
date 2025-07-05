import uvicorn

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    HttpUrl,
    ValidationError,
    field_validator,
)

from datetime import date

SQLITE_DB_NAME = "films.db"

async def create_tables() -> None:
    async with aiosqlite.connect(SQLITE_DB_NAME) as connection:
        cursor: aiosqlite.Cursor = await connection.cursor()
        await cursor.execute(
            """
                CREATE TABLE IF NOT EXISTS films (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    title     VARCHAR(30) NOT NULL,
                    director  VARCHAR(50) NOT NULL,
                    year      INTEGER NOT NULL,
                    rating    VARCHAR(10) NOT NULL 
                );
            """
        )
        await connection.commit()
        await connection.close()

app = FastAPI(on_startup=(create_tables,))


class FilmPydantic(BaseModel):
    title: str = Field(description="Title of the film", max_length=30)
    director: str = Field(description="Name of the director", min_length=3, max_length=50)
    year: int = Field(ge=0, le=date.today().year, description="Release year of the film")
    rating: float = Field(ge=0, le=10, description="Film rating from 0 to 10")


@app.post('/movies/')
async def create_movie(data: FilmPydantic) -> FilmPydantic:

    try:
        async with aiosqlite.connect(SQLITE_DB_NAME) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1 FROM films WHERE title = ?", (data.title,))
                db_film = await cursor.fetchone()
                print(db_film)

                if db_film is not None:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Film already exists.")

                await cursor.execute(
                    "INSERT INTO films (title, director, year, rating) VALUES (?, ?, ?, ?)",
                    (
                        data.title,
                        data.director,
                        data.year,
                        data.rating,
                    )
                )
                await connection.commit()

    except aiosqlite.Error as error:
        print(error)

    return data


@app.get('/movies/')
async def get_movies():
    try:
        async with aiosqlite.connect(SQLITE_DB_NAME) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT * FROM films")
                data = await cursor.fetchall()

    except aiosqlite.Error as error:
        print(error)

    return data


@app.get('/movies/{id}')
async def get_movie(id: int):
    try:
        async with aiosqlite.connect(SQLITE_DB_NAME) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT * FROM films WHERE id = ?", (id,))
                data = await cursor.fetchone()
                if data is None:
                    raise HTTPException(status_code=404, detail=f'Film with ID {id} not found')
    except aiosqlite.Error as error:
        print(error)
    else:
        return data


@app.delete('/movies/{id}')
async def delete_movies(id: int):
    try:
        async with aiosqlite.connect(SQLITE_DB_NAME) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT * FROM films WHERE id = ?", (id,))
                data = await cursor.fetchone()
                if data is None:
                    raise HTTPException(status_code=404, detail=f'Film with ID {id} not found')
                await cursor.execute("DELETE FROM films WHERE id = ?", (id,))
                await connection.commit()
    except aiosqlite.Error as error:
        print(error)
    else:
        return 'Deleted'


if __name__ == "__main__":
    uvicorn.run("pydantic_models:app", reload=True)