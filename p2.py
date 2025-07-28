import aiosqlite
import base64
import hashlib
from fastapi import FastAPI, Depends, HTTPException, Path, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, SecretStr
from typing import List, Optional
import uvicorn
from contextlib import asynccontextmanager

# OAuth2 схема
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

SQLITE_DB_NAME = "mydb.db"

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(SQLITE_DB_NAME) as db:
        # Создаем таблицу для пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
        """)
        
        # Создаем таблицу для информационных элементов
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
    description="API для хранения информации с аутентификацией",
    version="0.1.0",
    lifespan=lifespan
)

async def get_db():
    async with aiosqlite.connect(SQLITE_DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        yield db

# Модели данных
class Tag(BaseModel):
    name: str

class InfoItemBase(BaseModel):
    title: str
    content: str
    tags: List[Tag] = []

class InfoItemCreate(InfoItemBase):
    pass  # author_email будет браться из токена

class InfoItemInDB(InfoItemBase):
    id: int
    author_email: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserInDB(BaseModel):
    id: int
    name: str
    email: str

# Утилиты для работы с паролями (простое хеширование)
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

# Простая генерация токена
def create_access_token(email: str, name: str) -> str:
    token_data = f"{email}:{name}"
    return base64.urlsafe_b64encode(token_data.encode()).decode()

def decode_access_token(token: str) -> tuple:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        email, name = decoded.split(':', 1)
        return email, name
    except:
        return None, None

async def get_user_by_email(email: str, db: aiosqlite.Connection):
    query = "SELECT * FROM users WHERE email = ?"
    async with db.execute(query, (email,)) as cursor:
        row = await cursor.fetchone()
    return row

async def get_current_user(token: str = Depends(oauth2_scheme), db: aiosqlite.Connection = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    email, name = decode_access_token(token)
    if not email or not name:
        raise credentials_exception
    
    user = await get_user_by_email(email, db)
    if user is None:
        raise credentials_exception
    return UserInDB(**user)

# Регистрация пользователя
@app.post("/register", response_model=UserInDB, status_code=201)
async def register_user(user: UserCreate, db: aiosqlite.Connection = Depends(get_db)):
    # Проверяем, существует ли пользователь
    existing_user = await get_user_by_email(user.email, db)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Хешируем пароль
    password_hash = hash_password(user.password)
    
    # Создаем пользователя
    query = """
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
        RETURNING id, name, email;
    """
    async with db.execute(query, (user.name, user.email, password_hash)) as cursor:
        row = await cursor.fetchone()
    await db.commit()
    
    return UserInDB(**row)

# Вход пользователя
@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: aiosqlite.Connection = Depends(get_db)):
    user = await get_user_by_email(form_data.username, db)  # username содержит email
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(user["email"], user["name"])
    return Token(access_token=access_token, token_type="bearer")

# Получение информации о текущем пользователе
@app.get("/users/me", response_model=UserInDB)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user

# Защищенные маршруты для работы с информационными элементами
@app.post("/info/", response_model=InfoItemInDB, status_code=201)
async def create_info_item(
    item: InfoItemCreate, 
    current_user: UserInDB = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    tags_str = ", ".join(tag.name for tag in item.tags)
    query = """
        INSERT INTO info_items (title, content, tags, author_email)
        VALUES (?, ?, ?, ?)
        RETURNING id;
    """
    async with db.execute(query, (item.title, item.content, tags_str, current_user.email)) as cursor:
        row = await cursor.fetchone()
    await db.commit()
    
    return InfoItemInDB(
        id=row["id"],
        title=item.title,
        content=item.content,
        tags=item.tags,
        author_email=current_user.email
    )

@app.get("/info/", response_model=List[InfoItemInDB])
async def get_info_items(
    current_user: UserInDB = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    query = "SELECT * FROM info_items WHERE author_email = ?"
    async with db.execute(query, (current_user.email,)) as cursor:
        rows = await cursor.fetchall()
    
    items = []
    for row in rows:
        tags = [Tag(name=tag.strip()) for tag in row["tags"].split(",") if tag.strip()] if row["tags"] else []
        items.append(InfoItemInDB(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            tags=tags,
            author_email=row["author_email"]
        ))
    return items

@app.get("/info/{item_id}", response_model=InfoItemInDB)
async def get_info_item(
    item_id: int = Path(..., ge=1),
    current_user: UserInDB = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    query = "SELECT * FROM info_items WHERE id = ? AND author_email = ?"
    async with db.execute(query, (item_id, current_user.email)) as cursor:
        row = await cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    
    tags = [Tag(name=tag.strip()) for tag in row["tags"].split(",") if tag.strip()] if row["tags"] else []
    return InfoItemInDB(
        id=row["id"],
        title=row["title"],
        content=row["content"],
        tags=tags,
        author_email=row["author_email"]
    )

@app.put("/info/{item_id}", response_model=InfoItemInDB)
async def update_info_item(
    item: InfoItemCreate,
    item_id: int = Path(..., ge=1),
    current_user: UserInDB = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Проверяем, существует ли элемент и принадлежит ли он текущему пользователю
    check_query = "SELECT * FROM info_items WHERE id = ? AND author_email = ?"
    async with db.execute(check_query, (item_id, current_user.email)) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    tags_str = ", ".join(tag.name for tag in item.tags)
    update_query = """
        UPDATE info_items
        SET title = ?, content = ?, tags = ?
        WHERE id = ? AND author_email = ?;
    """
    await db.execute(update_query, (item.title, item.content, tags_str, item_id, current_user.email))
    await db.commit()
    
    return InfoItemInDB(
        id=item_id,
        title=item.title,
        content=item.content,
        tags=item.tags,
        author_email=current_user.email
    )

@app.delete("/info/{item_id}", status_code=204)
async def delete_info_item(
    item_id: int = Path(..., ge=1),
    current_user: UserInDB = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    check_query = "SELECT * FROM info_items WHERE id = ? AND author_email = ?"
    async with db.execute(check_query, (item_id, current_user.email)) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    delete_query = "DELETE FROM info_items WHERE id = ? AND author_email = ?"
    await db.execute(delete_query, (item_id, current_user.email))
    await db.commit()

if __name__ == '__main__':
    uvicorn.run("p2:app", reload=True)