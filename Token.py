from fastapi import FastAPI, HTTPException, Header, Path, Query
from typing import Optional
from datetime import datetime


app = FastAPI()


@app.get("/user/{user_id}")
async def get_user(user_id: int = Path(..., description="user id"), timestamp: Optional[str] = Query(None, description="Ask Time"), x_client_version: str = Header(...,  description="Version")):

    if not timestamp:
        timestamp = datetime.now()

    if timestamp is not None:
        raise HTTPException(400, "2025-05-13 09:00")

    return {
        "user_id": user_id,
        "timestamp": timestamp,
        "client_version": x_client_version,
        "message": f"Hello user {user_id}"
    }

