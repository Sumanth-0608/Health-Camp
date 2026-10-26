import os
import secrets
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _is_production():
    app_environment = os.environ.get("APP_ENV", "").strip().lower()
    vercel_environment = os.environ.get("VERCEL", "").strip().lower()
    return app_environment in {"prod", "production"} or vercel_environment in {"1", "true"}


def _database_uri():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    production = _is_production()

    if not database_url:
        if production:
            raise RuntimeError("DATABASE_URL is required in production and must point to hosted PostgreSQL.")
        return f"sqlite:///{BASE_DIR / 'wellness.db'}"

    try:
        database_url = make_url(database_url)
    except ArgumentError:
        raise RuntimeError("DATABASE_URL must be a valid SQLAlchemy database URL.") from None

    postgres_drivers = {"postgres", "postgresql", "postgresql+psycopg2"}
    if database_url.drivername in postgres_drivers:
        database_url = database_url.set(drivername="postgresql+psycopg")

    if production and database_url.drivername != "postgresql+psycopg":
        raise RuntimeError("DATABASE_URL must use a PostgreSQL URL in production.")
    if production and not database_url.host:
        raise RuntimeError("DATABASE_URL must include the PostgreSQL host from your database provider.")

    return database_url.render_as_string(hide_password=False)


def _secret_key():
    secret_key = os.environ.get("SECRET_KEY", "").strip()
    if _is_production() and not secret_key:
        raise RuntimeError("SECRET_KEY must be set to a private value in production.")
    return secret_key or secrets.token_urlsafe(32)


class Config:
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Uploads configuration
    UPLOAD_FOLDER = BASE_DIR / os.environ.get("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 8 * 1024 * 1024)) # 8MB
    
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ALLOWED_REPORT_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf"}
    
    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # Set to True when HTTPS is enabled
