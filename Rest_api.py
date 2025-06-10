import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Response, status, Request
from fastapi.templating import Jinja2Templates
from starlette.templating import _TemplateResponse
from enum import StrEnum
from pydantic import BaseModel, EmailStr, field_validator
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse


class BookCreate(BaseModel):
    name: str
    author: str
    years: float
    hou_match: int




class BookInfo(BaseModel):
    id: int
    name: str
    author: str
    years: float
    hou_match: int

templates = Jinja2Templates(directory="templates")
SQLITE_DB_NAME = "book.db"


async def get_connection():
    async with aiosqlite.connect(SQLITE_DB_NAME) as connection:
        connection.row_factory = aiosqlite.Row
        yield connection
        await connection.close()


async def create_tables() -> None:
    async with aiosqlite.connect(SQLITE_DB_NAME) as connection:
        cursor: aiosqlite.Cursor = await connection.cursor()
        await cursor.execute(
            """
                CREATE TABLE IF NOT EXISTS books (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            VARCHAR(30) NOT NULL,
                    author          VARCHAR(50) NOT NULL,
                    years           INTEGER,
                    hou_match       INTEGER
                );
            """
        )
        await connection.commit()


app = FastAPI(on_startup=(create_tables,), title="Corporation personal API.")



@app.post("/books/",status_code=status.HTTP_201_CREATED,response_class=Response,)
async def create_book(data: BookCreate, connection: aiosqlite.Connection = Depends(get_connection)) -> Response:


    print(f"Дані для створення співробітника: {data.model_dump()}")

    async with connection.cursor() as cursor:
        await cursor.execute("SELECT id FROM books WHERE author = ?;", (data.author,))
        db_book = await cursor.fetchone()

        if db_book is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Book exists.")

        await cursor.execute(
            "INSERT INTO books (name, author, years, hou_match) VALUES (?, ?, ?, ?) RETURNING *;",
            (data.name, data.author, data.years, data.hou_match),
        )
        last_inserted = await cursor.fetchone()
        await connection.commit()

        


@app.get("/books/", name="get_books", status_code=200, response_model=list[BookInfo])
async def get_books(connection: aiosqlite.Connection = Depends(get_connection)) -> list[BookInfo]:
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT id, name, author, years, hou_match FROM books;")
        db_book = await cursor.fetchall()

        return [BookInfo(**book).model_dump() for book in db_book]




@app.delete("/books/{book_id}", status_code=303, response_class=RedirectResponse)
async def delete_book(request: Request, book_id: int, connection: aiosqlite.Connection = Depends(get_connection)) -> RedirectResponse:
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT 1 FROM books WHERE id = ?;", (book_id,))
        db_book = await cursor.fetchall()

        if db_book is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found.")

        await cursor.execute("DELETE FROM books WHERE id = ?;", (book_id,))
        await connection.commit()

    return RedirectResponse(
        str(request.url_for("get_books")), status.HTTP_303_SEE_OTHER
    )