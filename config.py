import os


class Config:
    APP_ENV = os.environ.get("APP_ENV", "production").strip().lower()
    SECRET_KEY = os.environ.get("SECRET_KEY")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join("instance", "uploads")
    MAX_WORKERS = 2
    DEFAULT_BPM = 120.0
    MINIMUM_FREQUENCY_HZ = 80.0
    MAXIMUM_FREQUENCY_HZ = 3500.0
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
