import os
from pathlib import Path


def load_env(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env()


class Config:
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "buspass")
    TICKET_SIGNING_KEY = os.environ.get("TICKET_SIGNING_KEY", "")
    AES_KEY_HEX = os.environ.get("AES_KEY_HEX", "")
    LOG_FILE = os.environ.get("LOG_FILE", "app.log")
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    