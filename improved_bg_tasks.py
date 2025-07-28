import asyncio
import logging
import pathlib
import random
import time
from datetime import datetime
from typing import Optional

import aiofiles
import httpx
import pytest
import uvicorn
import yagmail
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from PIL import Image
import io

module_path = pathlib.Path(__file__).parent

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(module_path / 'app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# данные для отправки почты с вашего аккаунта Gmail
USER = "mikimv09@gmail.com"
PASSWORD = "12345678"  # В продакшене использовать переменные окружения

yag = yagmail.SMTP(user=USER, password=PASSWORD)


class EmailRequest(BaseModel):
    """Модель для запроса отправки email."""
    to_email: EmailStr = Field(examples=["user@example.com"])
    subject: str = Field(examples=["Test Subject"])
    message: str = Field(examples=["Hello, this is a test message!"])


class User(BaseModel):
    """Модель пользователя."""
    name: str = Field(examples=["John", "Josh"])
    email: EmailStr = Field(examples=["john@example.com"])
    phone: str = Field(examples=["+380661234567"])


class TaskStatus(BaseModel):
    """Модель статуса задачи."""
    task_id: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


# Глобальные переменные
users_db: list[User] = []
task_queue = asyncio.Queue()
task_statuses: dict[str, TaskStatus] = {}


def log_user_action(user_email: str, action: str, details: str = "") -> None:
    """Логирование действий пользователя."""
    logger.info(
        f"USER_ACTION | Email: {user_email} | Action: {action} | "
        f"Time: {datetime.now()} | Details: {details}"
    )


async def send_email(to_email: str, subject: str, message: str) -> None:
    """Отправление письма на почту."""
    try:
        log_user_action(to_email, "EMAIL_SEND_START", f"Subject: {subject}")
        
        yag.send(
            to=to_email,
            subject=subject,
            contents=message,
        )
        
        log_user_action(to_email, "EMAIL_SEND_SUCCESS", f"Subject: {subject}")
        logger.info(f"Email successfully sent to {to_email}")
        
    except Exception as e:
        log_user_action(to_email, "EMAIL_SEND_ERROR", f"Error: {str(e)}")
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        raise


def sync_task(t: int) -> None:
    """Симуляция задержки выполнения на `t` секунд."""
    time.sleep(t)
    logger.info(f"{t} seconds passed.")


async def download_file_by_name(file_path: str) -> None:
    """Загрузка файла большого размера."""
    try:
        log_user_action("system", "FILE_DOWNLOAD_START", f"Path: {file_path}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(file_path)
            response.raise_for_status()

        filename = pathlib.Path(file_path).name
        async with aiofiles.open(module_path / filename, mode="wb") as fp:
            await fp.write(response.content)

        log_user_action("system", "FILE_DOWNLOAD_SUCCESS", f"File: {filename}")
        logger.info(f"File '{filename}' has been downloaded.")
        
    except Exception as e:
        log_user_action("system", "FILE_DOWNLOAD_ERROR", f"Error: {str(e)}")
        logger.error(f"Failed to download file {file_path}: {str(e)}")
        raise


async def process_image(file_path: str, target_size: tuple[int, int] = (800, 600)) -> None:
    """Обработка изображения - изменение размера."""
    try:
        log_user_action("system", "IMAGE_PROCESS_START", f"File: {file_path}")
        
        # Открытие и обработка изображения
        with Image.open(file_path) as img:
            # Изменение размера с сохранением пропорций
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
            
            # Сохранение обработанного изображения
            processed_path = module_path / f"processed_{pathlib.Path(file_path).name}"
            img.save(processed_path)
        
        log_user_action("system", "IMAGE_PROCESS_SUCCESS", f"Processed: {processed_path}")
        logger.info(f"Image processed and saved as {processed_path}")
        
    except Exception as e:
        log_user_action("system", "IMAGE_PROCESS_ERROR", f"Error: {str(e)}")
        logger.error(f"Failed to process image {file_path}: {str(e)}")
        raise


async def simulate_io_delay() -> None:
    """Симуляция задержки доступа к стороннему API."""
    try:
        log_user_action("system", "API_REQUEST_START", "httpbin.org/delay/3")
        
        async with httpx.AsyncClient() as client:
            response = await client.get("https://httpbin.org/delay/3", timeout=10)
            response.raise_for_status()
            logger.info("API request completed successfully")
            
        log_user_action("system", "API_REQUEST_SUCCESS", "httpbin.org/delay/3")
        
    except Exception as e:
        log_user_action("system", "API_REQUEST_ERROR", f"Error: {str(e)}")
        logger.error(f"API request failed: {str(e)}")
        raise


async def add_user_to_file(name: str, email: EmailStr, phone: str) -> None:
    """Запись данных нового пользователя в текстовый файл."""
    try:
        log_user_action(str(email), "USER_FILE_WRITE_START", f"Name: {name}")
        
        # получаем всех пользователей со стороннего API
        async with httpx.AsyncClient() as client:
            response = await client.get("https://jsonplaceholder.typicode.com/users/")
            response.raise_for_status()

        # и добавляем их в файл
        async with aiofiles.open(module_path / "users.txt", "w", encoding="utf-8") as fp:
            for user in response.json():
                await fp.write(
                    f"name = {user['name']} | email = {user['email']} | phone = {user['phone']}\n\n"
                )
            # добавляем данные нового пользователя в файл
            await fp.write(f"name = {name} | email = {email} | phone = {phone}\n\n")

        log_user_action(str(email), "USER_FILE_WRITE_SUCCESS", f"Name: {name}")
        logger.info(f"User {name} added to file successfully")
        
    except Exception as e:
        log_user_action(str(email), "USER_FILE_WRITE_ERROR", f"Error: {str(e)}")
        logger.error(f"Failed to add user to file: {str(e)}")
        raise


async def process_task_queue():
    """Обработка задач из очереди с мониторингом."""
    logger.info("Task queue processor started")
    
    while True:
        try:
            task_info = await task_queue.get()
            task_id = task_info.get("id")
            task_func = task_info.get("func")
            
            if task_id in task_statuses:
                task_statuses[task_id].status = "processing"
                
            logger.info(f"Processing task {task_id}")
            
            try:
                await task_func
                if task_id in task_statuses:
                    task_statuses[task_id].status = "completed"
                    task_statuses[task_id].completed_at = datetime.now()
                logger.info(f"Task {task_id} completed successfully")
                
            except Exception as task_error:
                if task_id in task_statuses:
                    task_statuses[task_id].status = "failed"
                    task_statuses[task_id].error = str(task_error)
                    task_statuses[task_id].completed_at = datetime.now()
                logger.error(f"Task {task_id} failed: {str(task_error)}")
                
            finally:
                task_queue.task_done()
                
        except asyncio.CancelledError:
            logger.info("Task queue processor cancelled")
            break
        except Exception as e:
            logger.error(f"Error in task queue processor: {str(e)}")


async def startup_event() -> None:
    """Создание асинхронной задачи для обработчика асинхронной очереди."""
    asyncio.create_task(process_task_queue())
    logger.info("Application started")


app = FastAPI(title="Background Tasks Enhanced", on_startup=(startup_event,))


@app.post("/send-email", status_code=status.HTTP_202_ACCEPTED)
async def send_email_endpoint(
    email_request: EmailRequest, 
    bg_tasks: BackgroundTasks
) -> dict[str, str]:
    """Ендпоінт для відправлення електронних листів."""
    log_user_action(str(email_request.to_email), "EMAIL_REQUEST_RECEIVED", 
                   f"Subject: {email_request.subject}")
    
    bg_tasks.add_task(
        send_email,
        to_email=str(email_request.to_email),
        subject=email_request.subject,
        message=email_request.message
    )
    
    return {
        "message": f"Email sending request accepted for {email_request.to_email}",
        "status": "accepted"
    }


@app.post("/register", status_code=status.HTTP_201_CREATED, response_model=User)
async def user_registration(user_data: User, bg_tasks: BackgroundTasks) -> User:
    """Регистрация пользователя в базе данных."""
    log_user_action(str(user_data.email), "USER_REGISTRATION_START", 
                   f"Name: {user_data.name}")
    
    if user_data.email in {u.email for u in users_db}:
        log_user_action(str(user_data.email), "USER_REGISTRATION_ERROR", "User exists")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User exists.")

    users_db.append(user_data)
    log_user_action(str(user_data.email), "USER_REGISTRATION_SUCCESS", 
                   f"Name: {user_data.name}")

    # Добавление фоновых задач
    bg_tasks.add_task(simulate_io_delay)
    bg_tasks.add_task(
        add_user_to_file,
        name=user_data.name,
        email=user_data.email,
        phone=user_data.phone,
    )
    bg_tasks.add_task(
        send_email, 
        to_email=str(user_data.email),
        subject="Registration complete",
        message=f"Welcome to our site, '{user_data.email}'!"
    )
    bg_tasks.add_task(sync_task, t=10)

    logger.info(f"Background tasks scheduled for user {user_data.email}")
    return User(**user_data.model_dump())


@app.post("/upload-image", status_code=status.HTTP_202_ACCEPTED)
async def upload_image(
    file: UploadFile, 
    bg_tasks: BackgroundTasks,
    resize_width: int = 800,
    resize_height: int = 600
) -> dict[str, str]:
    """Загрузка и обработка изображений."""
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )
    
    log_user_action("system", "IMAGE_UPLOAD_START", f"Filename: {file.filename}")
    
    # Сохранение загруженного файла
    file_path = module_path / f"uploaded_{file.filename}"
    
    try:
        async with aiofiles.open(file_path, "wb") as f:
            content = await file.read()
            await f.write(content)
        
        # Добавление задачи обработки изображения
        bg_tasks.add_task(
            process_image, 
            str(file_path), 
            (resize_width, resize_height)
        )
        
        log_user_action("system", "IMAGE_UPLOAD_SUCCESS", f"Filename: {file.filename}")
        
        return {
            "message": f"Image {file.filename} uploaded and will be processed in background",
            "status": "accepted"
        }
        
    except Exception as e:
        log_user_action("system", "IMAGE_UPLOAD_ERROR", f"Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {str(e)}"
        )


async def run_task(name: str, delay: int) -> dict[str, str]:
    """Симуляция запуска задачи с именем `name` и задержкой `delay`."""
    logger.info(f"Task '{name}' with delay '{delay}' started.")
    await asyncio.sleep(delay)
    logger.info(f"Task '{name}' completed in {delay} seconds.")
    return {"success": f"Task '{name}' is done in {delay} seconds."}


@app.post("/add-task", status_code=status.HTTP_202_ACCEPTED)
async def add_task(name: str) -> dict[str, str]:
    """Добавление задачи в очередь с отслеживанием статуса."""
    task_id = f"task_{name}_{int(time.time())}"
    delay = random.randint(3, 10)
    
    # Создание записи о статусе задачи
    task_statuses[task_id] = TaskStatus(
        task_id=task_id,
        status="queued",
        created_at=datetime.now()
    )
    
    # Добавление в очередь
    await task_queue.put({
        "id": task_id,
        "func": run_task(name, delay)
    })
    
    log_user_action("system", "TASK_QUEUED", f"Task ID: {task_id}, Name: {name}")
    
    return {
        "message": f"Task '{name}' has been added to queue",
        "task_id": task_id,
        "status": "queued"
    }


@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str) -> TaskStatus:
    """Получение статуса задачи."""
    if task_id not in task_statuses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    return task_statuses[task_id]


@app.get("/queue-status")
async def get_queue_status() -> dict[str, int]:
    """Мониторинг состояния очереди."""
    return {
        "queue_size": task_queue.qsize(),
        "total_tasks": len(task_statuses),
        "completed_tasks": len([t for t in task_statuses.values() if t.status == "completed"]),
        "failed_tasks": len([t for t in task_statuses.values() if t.status == "failed"]),
        "processing_tasks": len([t for t in task_statuses.values() if t.status == "processing"])
    }


@app.get("/download", status_code=status.HTTP_202_ACCEPTED)
async def download_file(file_path: str, bg_tasks: BackgroundTasks) -> dict[str, str]:
    """Загрузка файла на фоне."""
    bg_tasks.add_task(download_file_by_name, file_path=file_path)
    log_user_action("system", "FILE_DOWNLOAD_QUEUED", f"Path: {file_path}")
    
    return {"success": "File will be downloaded in the background."}


# ТЕСТЫ
@pytest.mark.asyncio
async def test_send_email_endpoint():
    """Тест для проверки отправки email."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8000"
    ) as client:
        email_data = {
            "to_email": "test@example.com",
            "subject": "Test Subject",
            "message": "Test message content"
        }
        response = await client.post("/send-email", json=email_data)

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert "Email sending request accepted" in response.json()["message"]


@pytest.mark.asyncio
async def test_user_registration_with_logging():
    """Тест регистрации пользователя с логированием."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8000"
    ) as client:
        user_data = {
            "name": "Test User",
            "email": "testuser@example.com",
            "phone": "+380661234567"
        }
        response = await client.post("/register", json=user_data)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["name"] == "Test User"
    
    # Проверка, что пользователь добавлен в "базу данных"
    assert len(users_db) > 0
    assert any(user.email == "testuser@example.com" for user in users_db)


@pytest.mark.asyncio
async def test_image_upload():
    """Тест загрузки изображения."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8000"
    ) as client:
        # Создание тестового изображения
        test_image = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        test_image.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
        response = await client.post("/upload-image", files=files)

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert "uploaded and will be processed" in response.json()["message"]


@pytest.mark.asyncio
async def test_task_queue_with_status():
    """Тест добавления задачи в очередь с отслеживанием статуса."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8000"
    ) as client:
        response = await client.post("/add-task", params={"name": "test_task"})
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        task_id = response.json()["task_id"]
        
        # Проверка статуса задачи
        status_response = await client.get(f"/task-status/{task_id}")
        assert status_response.status_code == status.HTTP_200_OK
        assert status_response.json()["status"] in ["queued", "processing", "completed"]


@pytest.mark.asyncio
async def test_queue_monitoring():
    """Тест мониторинга очереди."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8000"
    ) as client:
        response = await client.get("/queue-status")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "queue_size" in data
        assert "total_tasks" in data
        assert "completed_tasks" in data
        assert "failed_tasks" in data


if __name__ == "__main__":
    uvicorn.run("improved_bg_tasks:app", port=8000, reload=True)