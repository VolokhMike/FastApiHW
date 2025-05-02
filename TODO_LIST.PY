import os 
from contextlib import asynccontextmanager

import aiomysql 
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel 

load_dotenv(os.path.abspath(f"{os.path.pardir}/.env"))


MYSQL_CONNECTION_DATA = {
    "host": os.environ.get("MYSQL_HOST"),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "user": os.environ.get("MYSQL_USER"),
    "password": os.environ.get("MYSQL_PASSWORD"),
    "db": os.environ.get("MYSQL_DB"),
}


async def get_mysql_connection() -> aiomysql.Connection:
    return await aiomysql.connect(**MYSQL_CONNECTION_DATA)


class Task(BaseModel):
    name: str 
    time: int 

class TaskInfo(Task):
    todo_id: int 
    name: str 
    time: int 


class TaskUpdate(BaseModel):
    name: str | None = None
    time: int | None = None 
    

app = FastAPI(title="TODO")


@app.post("/task/")
async def create_task(task: Task) -> TaskInfo:
    connection = await get_mysql_connection()

    try:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT 1 FROM todo WHERE name=%s;", (task.name,))
            db_tasks = await cursor.fetchone()

            if db_tasks is not None:
                raise HTTPException(400, "Tasks is alredy exists. ")
            
            await cursor.execute(
                "INSERT INTO todo (name, time) VALUES (%s, %s);",
                (
                    task.name,
                    task.time,

                ),
            )
            await connection.commit()
            await cursor.execute("SELECT LAST_INSERT_ID();")
            user_id = await cursor.fetchone()
    except aiomysql.Error as e:
        raise e
    finally:
        await connection.ensure_closed()
    
    return TaskInfo(**task.model_dump(), todo_id=user_id[0])



@app.get("/task/")
async def get_task(
    limit: int = Query(default=100, description="Кількість тасков для отримання."),) -> list[TaskInfo]:
    connection = await get_mysql_connection()

    try:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM todo LIMIT %s;", (limit,))
            db_tasks = await cursor.fetchall()
    except aiomysql.Error as e:
        raise e
    finally:
        await connection.ensure_closed()
    print(db_tasks)
    return [TaskInfo(**data) for data in db_tasks]


@app.get("/task/{task_id}")
async def get_task(task_id: int) -> TaskInfo:
    connection = await get_mysql_connection()

    try:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM todo WHERE todo_id=%s", task_id)
            db_tasks = await cursor.fetchone()

            if db_tasks is None:
                raise HTTPException(404, "Task does not exist.")

    except aiomysql.Error as e:
        raise e
    finally:
        await connection.ensure_closed()

    return TaskInfo(**db_tasks)


@app.put("/task/{task_id}")
async def update_task(task_id: int, update_data: TaskUpdate) -> TaskInfo:
    connection = await get_mysql_connection()

    try:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM todo WHERE todo_id=%s;", (task_id,))
            db_tasks = await cursor.fetchone()

            if db_tasks is None:
                raise HTTPException(404, "Task does not exist.")

            await cursor.execute(
                "UPDATE todo SET name=%s, time=%s WHERE todo_id=%s",
                (
                    update_data.name,
                    update_data.time,
                    task_id,
                ),
            )
            await connection.commit()
    except aiomysql.Error as e:
        raise e
    finally:
        await connection.ensure_closed()

    return TaskInfo(**update_data.model_dump(), todo_id=db_tasks["todo_id"])


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int) -> JSONResponse:
    connection = await get_mysql_connection()

    try:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT 1 FROM todo WHERE todo_id=%s;", (task_id,))
            db_tasks = await cursor.fetchone()
            if db_tasks is None:
                raise HTTPException(404, "Task does not exist.")

            await cursor.execute("DELETE FROM todo WHERE todo_id=%s", (task_id,))
            await connection.commit()
    except aiomysql.Error as e:
        raise e
    finally:
        await connection.ensure_closed()

    return JSONResponse("Task has been deleted.", status_code=200)
