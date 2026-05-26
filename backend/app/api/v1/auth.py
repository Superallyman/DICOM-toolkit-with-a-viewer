from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel

from app.utilities.auth_utils import create_jwt_token, create_refresh_token, decode_jwt_token
from config.config import CLIENT_CREDENTIALS

router = APIRouter(tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/authenticator")
async def authenticator(username: str = Form(...), password: str = Form(...)):
    if username in CLIENT_CREDENTIALS and CLIENT_CREDENTIALS[username] == password:
        return {
            "access_token": create_jwt_token(username),
            "refresh_token": create_refresh_token(username),
            "token_type": "bearer",
            "message": "Authentication successful.",
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/auth/refresh")
async def refresh_access_token(request: RefreshRequest):
    try:
        payload = decode_jwt_token(request.refresh_token)
        username = payload.get("sub")
        if username is None or payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        return {"access_token": create_jwt_token(username)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token refresh failed")
