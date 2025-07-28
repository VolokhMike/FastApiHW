import aiosqlite
import base64
from fastapi import FastAPI, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, EmailStr, SecretStr, Field
from typing import List
import uvicorn
from contextlib import asynccontextmanager
from fastapi.security import (
    HTTPBasic,
    HTTPBasicCredentials,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
security = HTTPBasic()


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
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                password INTEGER,
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
    tags: List[Tag] = Field(default_factory=list)


class InfoUSerBase(BaseModel):
    title: str
    content: str
    tags: List[Tag] = Field(default_factory=list)

class InfoItemCreate(InfoItemBase):
    author_email: str

class InfoItemInDB(InfoItemBase):
    id: int
    author_email: str

class Token(BaseModel):
    token_type: str
    access_token: str

class UsersInfo(BaseModel):
    name: str
    password: SecretStr


class UserShow(UsersInfo):
    id: int

class UserCreate(UsersInfo):
    name: str
    author_email: EmailStr
    password: str



@app.post(
    "/info/", 
    response_model=InfoItemInDB, 
    status_code=201,
    tags=["items"],
    summary="Create items",
    description="Endpoint used for creating itema",
    response_description="Create item",
    operation_id="create-item",# уникальные у каждого ендпоинта
    include_in_schema=True,
    name="create-item",# уникальные у каждого ендпоинта
    )
async def create_info_item(item: InfoItemCreate, db: aiosqlite.Connection = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_email = await decode_token(token=token) #поиск юзера по токен 
    
    async with db.cursor() as cursor:
        await cursor.execute("SELECT 1 FROM users WHERE author_email = ?;", (user_email,))
        db_user = await cursor.fetchone()

        if db_user is None:
            raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
            )
    
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
async def update_info_item(item_id: int = Path(..., ge=1), item: InfoItemCreate = Depends(), db: aiosqlite.Connection = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_email = await decode_token(token=token)
    
    async with db.cursor() as cursor:
        await cursor.execute("SELECT 1 FROM users WHERE author_email = ?;", (user_email,))
        db_user = await cursor.fetchone()

        if db_user is None:
            raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
            )
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
async def delete_info_item(item_id: int = Path(..., ge=1), db: aiosqlite.Connection = Depends(get_db),  token: str = Depends(oauth2_scheme)):
    user_email = await decode_token(token=token) #поиск юзера по токен 
    
    async with db.cursor() as cursor:
        await cursor.execute("SELECT 1 FROM users WHERE author_email = ?;", (user_email,))
        db_user = await cursor.fetchone()

        if db_user is None:
            raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
            )
    
    
    check_query = "SELECT * FROM info_items WHERE id = ?"
    async with db.execute(check_query, (item_id,)) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    delete_query = "DELETE FROM info_items WHERE id = ?"
    await db.execute(delete_query, (item_id,))
    await db.commit()



@app.post(
    "/register", 
    status_code=status.HTTP_200_OK,
    response_model=list[UserShow],
    tags=["register"],
    summary="User exist ",
    description="Endpoint used for getting registered users",
    response_description="Users is register",
    operation_id="user-register",
    include_in_schema=True,
    name="user-register",
    )
async def user_registration(user_data: UserCreate, connection: aiosqlite.Connection = Depends(get_db)) -> UserShow:

    async with connection.cursor() as cursor:
        await cursor.execute("SELECT 1 FROM users WHERE author_email = ?;", (user_data.author_email,))
        db_user = await cursor.fetchone()

        if db_user is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "User exists.")

        await cursor.execute(
            "INSERT INTO users (name, password, author_email) VALUES (?, ?, ?) RETURNING id;",
            (
                user_data.name,
                user_data.password,
                user_data.author_email
            ),
        )

        last_inserted = await cursor.fetchone()
        await connection.commit()

    return UserShow(**user_data.model_dump(), id=last_inserted["id"])

async def decode_token(token: str):
    try:
        # email-name.split("-")[0] --> email
        decoded_user_email = (
            base64.urlsafe_b64decode(token).split(b"-")[0].decode("utf-8")
        )
    except (UnicodeDecodeError, ValueError):
        return None

    return decoded_user_email

@app.post(
    "/token", 
    response_model=Token,
    status_code=status.HTTP_200_OK,
    tags=["users"],
    summary="User token",
    description="Get user token ",
    responses={
        201: {"description": "User alredy exist "},
        400: {"description": "User is not regestration "},
    },
    operation_id="user-token",
    include_in_schema=True,
    name="user-token",)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),connection: aiosqlite.Connection = Depends(get_db),) -> Token:
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT * FROM users WHERE author_email = ?;", (form_data.username,)
        )
        db_user = await cursor.fetchone()
        if db_user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User does not exist.")
    user = UserShow(**db_user)
    
    if user.password.get_secret_value() != form_data.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect password.")
    
    return Token(
        access_token=base64.urlsafe_b64encode(
            f"{form_data.username}-{user.name}".encode("utf-8")
        ).decode("utf-8"),
        token_type="bearer",
    )




if __name__ == '__main__':
    uvicorn.run("Info_hub:app", reload=True)
