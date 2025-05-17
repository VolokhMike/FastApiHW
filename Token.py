from fastapi import FastAPI, HTTPException, Header, Path, Query
from typing import Optional
from datetime import datetime

app = FastAPI()


@app.get("/user/{user_id}")
async def get_user( user_id: int = Path(..., description="user id."), timestamp: Optional[str] = Query(None, description="Time for question"), x_client_version: str = Header(...,  description="Version")):
    if not timestamp:
        timestamp = datetime.now()

    return {
        "user_id": user_id,
        "timestamp": timestamp,
        "client_version": x_client_version,
        "message": f"Hello user {user_id}"
    }



