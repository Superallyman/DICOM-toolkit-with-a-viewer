import logging
import os

import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-before-production")
API_KEYS = {
    key.strip()
    for key in os.getenv("API_KEYS", "client1-api-key,client2-api-key").split(",")
    if key.strip()
}
CORS_ERROR_ORIGIN = os.getenv("CORS_ERROR_ORIGIN", "http://localhost:3000")


ALLOWED_PATH_PREFIXES = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/v1/authenticator",
    "/v1/auth/refresh",
    "/v1/healthcheck",
    "/v1/health/live",
    "/v1/health/ready",
    # Viewer and static routes.
    "/v1/viewer",
    "/v1/manifest.json",
    "/v1/assets",
    "/v1/favicon.ico",
    # Some OHIF builds request these at the server root.
    "/app.bundle",
    "/app-config",
    "/init-service-worker",
    # Public download and DICOMweb read endpoints.
    "/v1/files",
    "/v1/dicomweb",
]


def verify_jwt_token(token: str):
    """Verify a JWT without logging bearer-token material."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        logging.debug("JWT token validated for subject=%s", payload.get("sub"))
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


async def authentication_middleware(request: Request, call_next):
    """Protect private API endpoints while allowing public viewer/static routes."""
    try:
        if request.method == "OPTIONS":
            return await call_next(request)

        if any(request.url.path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        api_key = request.headers.get("x-api-key")
        logging.debug("Auth header present: %s", bool(auth_header))

        if api_key and api_key in API_KEYS:
            logging.info("Authenticated with API key")
        elif auth_header and "Bearer" in auth_header:
            token = auth_header.split(" ", 1)[1]
            verify_jwt_token(token)
            logging.info("Authenticated with JWT")
        else:
            raise HTTPException(status_code=403, detail="Unauthorized")

        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={"Access-Control-Allow-Origin": CORS_ERROR_ORIGIN},
        )
