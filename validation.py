import aiosqlite
from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List
import uvicorn

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                name TEXT NOT NULL,
                email TEXT PRIMARY KEY
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price_per_unit REAL NOT NULL,
                FOREIGN KEY (user_email) REFERENCES users(email)
            );
        """)
        await db.commit()

app = FastAPI(on_startup=[init_db])

async def get_db():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        yield db

class Order(BaseModel):
    product_name: str = Field(..., min_length=1, description="Product name cannot be empty")
    quantity: int = Field(default=1, gt=0, description="The number must be a positive number")
    price_per_unit: float = Field(..., gt=0, description="The unit price shall be positive")

    @field_validator("product_name")
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("The product name cannot be empty or only spaces")
        return v

class User(BaseModel):
    name: str
    email: EmailStr
    orders: List[Order] = Field(default_factory=list)

@app.post("/users", response_model=User)
async def create_user(user: User, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT email FROM users WHERE email = ?", (user.email,)) as cursor:
        existing_user = await cursor.fetchone()
        
        if existing_user:
            raise HTTPException(status_code=400, detail="A user with such an email already exists.")
    
    await db.execute("INSERT INTO users (name, email) VALUES (?, ?)", (user.name, user.email))

    for order in user.orders:
        await db.execute(
            "INSERT INTO orders (user_email, product_name, quantity, price_per_unit) VALUES (?, ?, ?, ?)",
            (user.email, order.product_name, order.quantity, order.price_per_unit)
        )
    
    await db.commit()
    
    return user

@app.get("/users", response_model=User)
async def get_user(email: EmailStr = Query(..., description="Enter a valid email"), db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT name, email FROM users WHERE email = ?", (email,)) as cursor:
        user_row = await cursor.fetchone()
        
        if not user_row:
            raise HTTPException(status_code=404, detail="No user found.")
    
    async with db.execute("SELECT product_name, quantity, price_per_unit FROM orders WHERE user_email = ?", (email,)) as cursor:
        order_rows = await cursor.fetchall()
    
    orders = [
        Order(
            product_name=row["product_name"], 
            quantity=row["quantity"], 
            price_per_unit=row["price_per_unit"]
        ) 
        for row in order_rows
    ]
    
    return User(name=user_row["name"], email=user_row["email"], orders=orders)

if __name__ == "__main__":
    uvicorn.run("validation:app", reload=True)