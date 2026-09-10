"""Authentication endpoints: signup, login, and current-user.

POST /api/auth/signup — create an account, return a bearer token.
POST /api/auth/login  — verify credentials, return a bearer token.
GET  /api/auth/me     — return the authenticated user (requires a token).

Also exposes ``get_current_user``, a FastAPI dependency other routes use to
require authentication.
"""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.logger import get_logger
from app.models.schemas import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    UserOut,
)
from app.services import auth_service

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Ensure the user table exists as soon as the module is imported.
auth_service.init_db()

_bearer = HTTPBearer(auto_error=True)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """Resolve the current user from the bearer token, or raise 401."""
    try:
        user_id = auth_service.decode_token(creds.credentials)
    except jwt.PyJWTError as exc:  # expired, bad signature, malformed, etc.
        raise _CREDENTIALS_EXC from exc
    user = auth_service.get_user_by_id(user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    return user


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def signup(body: SignupRequest) -> AuthResponse:
    try:
        user = auth_service.create_user(body.name, body.email, body.password)
    except auth_service.EmailExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    token = auth_service.create_access_token(user["id"])
    return AuthResponse(access_token=token, user=UserOut(**user))


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in and receive a token",
)
def login(body: LoginRequest) -> AuthResponse:
    try:
        user = auth_service.authenticate(body.email, body.password)
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    token = auth_service.create_access_token(user["id"])
    return AuthResponse(access_token=token, user=UserOut(**user))


@router.get("/me", response_model=UserOut, summary="Current authenticated user")
def me(user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(**user)
