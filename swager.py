import base64

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, SecretStr

DATABASE_NAME = "users.db"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_database():
    """Create and return database connection."""
    async with aiosqlite.connect(DATABASE_NAME) as db_connection:
        db_connection.row_factory = aiosqlite.Row
        yield db_connection
        await db_connection.close()


async def initialize_tables() -> None:
    async with aiosqlite.connect(DATABASE_NAME) as db_connection:
        db_cursor: aiosqlite.Cursor = await db_connection.cursor()
        await db_cursor.execute(
            """
                CREATE TABLE IF NOT EXISTS users (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    name      VARCHAR(30) NOT NULL,
                    email     VARCHAR(50) NOT NULL,
                    password  VARCHAR(30) NOT NULL,
                    is_active BOOLEAN NOT NULL CHECK (is_active IN (0, 1))
                );
            """
        )
        await db_connection.commit()
        await db_connection.close()


app = FastAPI(on_startup=(initialize_tables,), docs_url="/docs", redoc_url="/redoc")


class UserCreate(BaseModel):
    """Model for user creation."""

    name: str = Field(
        description="User's name", min_length=3, examples=["Alice", "Bob", "Charlie"]
    )
    email: EmailStr = Field(description="User's email address", examples=["user@example.com"])
    password: SecretStr


class UserDisplay(UserCreate):
    """Model for displaying user data."""

    id: int = Field(description="User ID", gt=0)
    is_active: bool = Field(
        default=False, description="Indicates if the user is active."
    )


class AccessToken(BaseModel):
    """Model for access token."""

    token_type: str = Field(description="Type of token", examples=["bearer"])
    access_token: str = Field(description="Encoded token", examples=["dXNlckBleGFtcGxlLmNvbS1BbGljZQ=="])


async def decode_access_token(token: str):
    """Decode the access token to extract the user's email."""
    try:
        user_email = (
            base64.urlsafe_b64decode(token).split(b"-")[0].decode("utf-8")
        )
    except (UnicodeDecodeError, ValueError):
        return None

    return user_email


@app.get(
    "/users/me",
    status_code=status.HTTP_200_OK,
    response_model=UserDisplay,
    tags=["users"],
    summary="Get current authenticated user",
    description="Fetch the data of the currently authenticated and active user",
    responses={
        200: {"description": "Success. User data returned."},
        401: {"description": "Invalid authentication credentials."},
        400: {"description": "User is not active."},
    },
    operation_id="get_current_user",
    include_in_schema=True,
    name="get_current_user",
)
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db_connection: aiosqlite.Connection = Depends(get_database),
) -> UserDisplay:
    """Retrieve current authenticated user data."""
    user_email = await decode_access_token(token)

    async with db_connection.cursor() as db_cursor:
        await db_cursor.execute("SELECT * FROM users WHERE email = ?;", (user_email,))
        user_row = await db_cursor.fetchone()

        if user_row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user = UserDisplay(**user_row)

    if not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User is not active.")

    return user


@app.post(
    "/token",
    response_model=AccessToken,
    tags=["auth"],
    summary="Generate access token from email and password",
    description="Authenticate and receive an access token",
    responses={
        200: {"description": "Success. Token returned."},
        404: {"description": "User not found."},
        400: {"description": "Incorrect password."},
    },
    operation_id="login",
    include_in_schema=True,
    name="login",
)
async def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    db_connection: aiosqlite.Connection = Depends(get_database),
) -> AccessToken:
    """Authenticate user and return access token."""
    async with db_connection.cursor() as db_cursor:
        await db_cursor.execute("SELECT * FROM users WHERE email = ?;", (credentials.username,))
        user_row = await db_cursor.fetchone()

        if user_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User does not exist.")

    user = UserDisplay(**user_row)

    if user.password.get_secret_value() != credentials.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect password.")

    token_value = base64.urlsafe_b64encode(
        f"{user.email}-{user.name}".encode("utf-8")
    ).decode("utf-8")

    return AccessToken(access_token=token_value, token_type="bearer")


@app.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserDisplay,
    tags=["users"],
    summary="Register a new user",
    description="Create a new user in the system",
    responses={
        201: {"description": "Success. User created."},
        400: {"description": "User already exists."},
    },
    operation_id="register_user",
    include_in_schema=True,
    name="register_user",
)
async def register_user(
    user_input: UserCreate, db_connection: aiosqlite.Connection = Depends(get_database)
) -> UserDisplay:
    """Register a new user to the database."""
    async with db_connection.cursor() as db_cursor:
        await db_cursor.execute("SELECT 1 FROM users WHERE email = ?;", (user_input.email,))
        existing = await db_cursor.fetchone()

        if existing is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "User already exists.")

        await db_cursor.execute(
            "INSERT INTO users (name, email, password, is_active) VALUES (?, ?, ?, ?) RETURNING id;",
            (
                user_input.name,
                user_input.email,
                user_input.password.get_secret_value(),
                True,
            ),
        )

        new_user_id = await db_cursor.fetchone()
        await db_connection.commit()

    return UserDisplay(
        **user_input.model_dump(exclude={"is_active"}),
        id=new_user_id["id"],
        is_active=True,
    )


@app.get(
    "/users/",
    status_code=status.HTTP_200_OK,
    response_model=list[UserDisplay],
    tags=["users"],
    summary="Retrieve all users with optional limit",
    description="Get a list of users from the database with an optional limit",
    response_description="List of users returned",
    operation_id="get_users",
    include_in_schema=True,
    name="get_users",
)
async def get_users(
    limit: int = Query(default=10, description="Max number of users to return", gt=0),
    db_connection: aiosqlite.Connection = Depends(get_database),
) -> list[UserDisplay]:
    """Fetch users from the database with a given limit."""
    async with db_connection.cursor() as db_cursor:
        await db_cursor.execute("SELECT * FROM users LIMIT ?;", (limit,))
        users = await db_cursor.fetchall()

    return [UserDisplay(**user) for user in users]
