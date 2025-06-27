import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, SecretStr
from typing import List
import uvicorn
from contextlib import asynccontextmanager


SQLITE_DB_NAME = "mydb.db"

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(SQLITE_DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS info_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT,
                author_email TEXT NOT NULL
            );
        """)
        await db.commit()
    yield


app = FastAPI(
    title="InfoHub API",
    description="API для хранения информации",
    version="0.1.0",
    lifespan=lifespan
)

async def get_db():
    async with aiosqlite.connect(SQLITE_DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        yield db


class Tag(BaseModel):
    name: str

class InfoItemBase(BaseModel):
    title: str
    content: str
    tags: List[Tag] = []

class InfoItemCreate(InfoItemBase):
    author_email: str

class InfoItemInDB(InfoItemBase):
    id: int
    author_email: str

async def decode_token(token: str):
    try:
        decoded_user_email = (
            base64.urlsafe_b64decode(token).split(b"-")[0].decode("utf-8")
        )
    except (UnicodeDecodeError, ValueError):
        return None

    return decoded_user_email


@app.post("/info/", response_model=InfoItemInDB, status_code=201)
async def create_info_item(item: InfoItemCreate, db: aiosqlite.Connection = Depends(get_db)):
    tags_str = ", ".join(tag.name for tag in item.tags)
    query = """
        INSERT INTO info_items (title, content, tags, author_email)
        VALUES (?, ?, ?, ?)
        RETURNING id;
    """
    async with db.execute(query, (item.title, item.content, tags_str, item.author_email)) as cursor:
        row = await cursor.fetchone()
    await db.commit()
    return InfoItemInDB(id=row["id"], **item.dict())

@app.post(
    "/token",
    response_model=Token,
    tags=["auth"],
    summary="Get access token by provided email and password",
    description="Endpoint used for auth purposes. Access token will be returned after calling it",
    responses={
        200: {"description": "Success. Token returned"},
        404: {"description": "User not found"},
        400: {"description": "Incorrect password provided"},
    },
    operation_id="get-access-token",
    include_in_schema=True,
    name="get-token",
)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    connection: aiosqlite.Connection = Depends(get_db),
) -> Token:
    """
    Отримання токену автентифікації для доступу до захищених ендпоінтів.
    Буде автоматично викликаний при авторизації після вводу email та пароля в SwaggerUI
    ('Authorize' кнопка справа вгорі).
    """
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT * FROM users WHERE email = ?;", (form_data.username,)
        )
        db_user = await cursor.fetchone()

        if db_user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User does not exist.")

    user = UserShow(**db_user)

    if user.password.get_secret_value() != form_data.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect password.")

    return Token(
        access_token=base64.urlsafe_b64encode(
            f"{user.email}-{user.name}".encode("utf-8")
        ).decode("utf-8"),
        token_type="bearer",
    )


if __name__ == '__main__':
    uvicorn.run("main:app", reload=True)
