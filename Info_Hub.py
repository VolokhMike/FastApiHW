import aiosqlite
import base64
from fastapi import FastAPI, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, EmailStr, SecretStr
from typing import List
import uvicorn
from contextlib import asynccontextmanager
from fastapi.security import (
    HTTPBasic,
    HTTPBasicCredentials,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
)

security = HTTPBasic()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SQLITE_DB_NAME = "mydb.db"

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(SQLITE_DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS info_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                name TEXT NOT NULL,
                password INTEGER,
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

class Token(BaseModel):
    token_type: str
    access_token: str

class UserShow(InfoItemBase):
    id: int

class UserCreate(InfoItemBase):
    name: str
    password: SecretStr



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


@app.put("/info/{item_id}", response_model=InfoItemInDB)
async def update_info_item(item_id: int = Path(..., ge=1), item: InfoItemCreate = Depends(), db: aiosqlite.Connection = Depends(get_db)):
    check_query = "SELECT * FROM info_items WHERE id = ?"
    async with db.execute(check_query, (item_id,)) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    tags_str = ", ".join(tag.name for tag in item.tags)
    update_query = """
        UPDATE info_items
        SET title = ?, content = ?, tags = ?, author_email = ?
        WHERE id = ?;
    """
    await db.execute(update_query, (item.title, item.content, tags_str, item.author_email, item_id))
    await db.commit()
    return InfoItemInDB(id=item_id, **item.dict())


@app.delete("/info/{item_id}", status_code=204)
async def delete_info_item(item_id: int = Path(..., ge=1), db: aiosqlite.Connection = Depends(get_db)):
    check_query = "SELECT * FROM info_items WHERE id = ?"
    async with db.execute(check_query, (item_id,)) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    delete_query = "DELETE FROM info_items WHERE id = ?"
    await db.execute(delete_query, (item_id,))
    await db.commit()



async def decode_token(token: str):
    try:
        decoded_user_email = (
            base64.urlsafe_b64decode(token).split(b"-")[0].decode("utf-8")
        )
    except (UnicodeDecodeError, ValueError):
        return None
    return decoded_user_email

@app.get("/users/me/token", status_code=status.HTTP_200_OK, response_model=UserShow)
async def get_user_me_token(token: str = Depends(oauth2_scheme), connection: aiosqlite.Connection = Depends(get_db),) -> UserShow:
    decoded_email = await decode_token(token)
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT * FROM info_items WHERE name = ?;", (decoded_email,))
        db_user = await cursor.fetchone()
        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    decoded_user = UserShow(**db_user)
    if not decoded_user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User is not active.")
    return decoded_user

@app.get("/users/me/basic", status_code=status.HTTP_200_OK, response_model=UserShow)
async def get_user_me_basic(credentials: HTTPBasicCredentials = Depends(security), connection: aiosqlite.Connection = Depends(get_db),) -> UserShow:
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT * FROM info_items WHERE name = ? AND password = ?;",
            (credentials.username, credentials.password),
        )
        db_user = await cursor.fetchone()
        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Basic"},
            )
    decoded_user = UserShow(**db_user)
    if not decoded_user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User is not active.")
    return decoded_user

@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),connection: aiosqlite.Connection = Depends(get_db),) -> Token:
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT * FROM info_items WHERE name = ?;", (form_data.username,)
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
    uvicorn.run("Info_Hub:app", reload=True)
