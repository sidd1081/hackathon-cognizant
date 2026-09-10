"""Authentication service: SQLAlchemy user store + JWT tokens.

Uses PostgreSQL in production (set ``DATABASE_URL``) and falls back to a local
SQLite file for dev/demo. Passwords are hashed with PBKDF2-HMAC-SHA256 (Python
stdlib — no bcrypt build dependency); the plaintext is never stored or logged.
Access tokens are signed JWTs (HS256).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# backend/app/services/auth_service.py -> parents[2] == backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH: Path = _BACKEND_ROOT / "data" / "auth.db"

# PBKDF2 parameters.
_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


class AuthError(Exception):
    """Base class for auth failures."""


class EmailExistsError(AuthError):
    """Signup attempted with an email that is already registered."""


class InvalidCredentialsError(AuthError):
    """Login failed (unknown email or wrong password)."""


# --- password hashing ---------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 hash: ``pbkdf2_sha256$iter$salt$hash``."""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify a password against a stored PBKDF2 hash."""
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        assert algo == f"pbkdf2_{_PBKDF2_ALGO}"
        dk = hashlib.pbkdf2_hmac(
            _PBKDF2_ALGO,
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, AssertionError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


# --- database (SQLAlchemy; Postgres or SQLite) --------------------------------

def _resolve_db_url() -> str:
    """Return a SQLAlchemy URL, normalizing Postgres URLs to the psycopg3 driver."""
    url = settings.database_url
    if not url:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    # Managed Postgres providers hand out postgres:// or postgresql:// URLs;
    # point them at psycopg3 (the driver we install).
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


_DB_URL = _resolve_db_url()
_is_sqlite = _DB_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_engine(_DB_URL, pool_pre_ping=True, connect_args=_connect_args)

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(80), nullable=False),
    # Emails are stored lowercased, so a plain unique constraint is
    # case-insensitive in practice across both SQLite and Postgres.
    Column("email", String(254), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)


def init_db(retries: int = 10, delay: float = 1.5) -> None:
    """Create the users table if needed, retrying while the DB comes up.

    The retry loop lets the backend start slightly before Postgres is ready
    (e.g. under docker-compose) without crashing.
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            metadata.create_all(engine)
            logger.info(
                "Auth DB ready (%s)", "sqlite" if _is_sqlite else "postgresql"
            )
            return
        except OperationalError as exc:  # DB not accepting connections yet
            last_error = exc
            logger.warning(
                "Auth DB not ready (attempt %d/%d); retrying…", attempt, retries
            )
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def _row_to_user(row) -> dict:
    return {"id": row.id, "name": row.name, "email": row.email}


def create_user(name: str, email: str, password: str) -> dict:
    """Create a user and return the public dict. Raises EmailExistsError."""
    email = email.strip().lower()
    values = {
        "name": name.strip(),
        "email": email,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with engine.begin() as conn:
            result = conn.execute(insert(users).values(**values))
            user_id = int(result.inserted_primary_key[0])
    except IntegrityError as exc:
        raise EmailExistsError("An account with this email already exists.") from exc
    logger.info("Created user id=%d", user_id)
    return {"id": user_id, "name": values["name"], "email": email}


def authenticate(email: str, password: str) -> dict:
    """Verify credentials and return the public user dict, else raise."""
    email = email.strip().lower()
    with engine.connect() as conn:
        row = conn.execute(
            select(users).where(users.c.email == email)
        ).first()
    if row is None or not verify_password(password, row.password_hash):
        raise InvalidCredentialsError("Incorrect email or password.")
    return _row_to_user(row)


def get_user_by_id(user_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(users).where(users.c.id == user_id)
        ).first()
    return _row_to_user(row) if row else None


# --- JWT ----------------------------------------------------------------------

def create_access_token(user_id: int) -> str:
    """Create a signed JWT whose subject is the user id."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> int:
    """Decode a JWT and return the user id. Raises jwt exceptions on failure."""
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    return int(payload["sub"])
