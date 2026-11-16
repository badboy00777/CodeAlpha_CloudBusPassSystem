import uuid
from pathlib import Path

import pymysql
import pytest

from app.config import Config
from app.db import get_connection

TEST_DB = "buspass_test"
SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


@pytest.fixture(scope="session")
def db_ready():
    Config.DB_NAME = TEST_DB
    admin = pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            sql = SCHEMA.read_text(encoding="utf-8").replace("buspass", TEST_DB)
            for statement in sql.split(";"):
                if statement.strip():
                    cur.execute(statement)
    finally:
        admin.close()
    yield TEST_DB


@pytest.fixture
def conn(db_ready):
    c = get_connection()
    with c.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for table in ("bookings", "route_capacity", "users"):
            cur.execute(f"TRUNCATE TABLE {table}")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        cur.execute("UPDATE routes SET daily_capacity=40")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def make_user(conn):
    def _make(name="Ali Raza"):
        email = f"{uuid.uuid4().hex[:10]}@example.com"
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)",
                (name, email, "test-hash"),
            )
            user_id = cur.lastrowid
        conn.commit()
        return user_id

    return _make


@pytest.fixture
def sold_count(conn):
    def _count(route="KHI-01"):
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(c.sold), 0) AS n FROM route_capacity c "
                "JOIN routes r ON r.id = c.route_id WHERE r.code = %s",
                (route,),
            )
            n = int(cur.fetchone()["n"])
        conn.commit()
        return n

    return _count


@pytest.fixture
def booking_count(conn):
    def _count():
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM bookings")
            n = int(cur.fetchone()["n"])
        conn.commit()
        return n

    return _count

from app.security import hash_password


@pytest.fixture
def flask_app(conn, tmp_path):
    from app import create_app

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-for-sessions",
            "TICKET_SIGNING_KEY": "unit-test-signing-key-not-a-real-secret",
            "AES_KEY_HEX": "ab" * 32,
            "LOG_FILE": str(tmp_path / "app.log"),
        }
    )
    yield application
    for handler in list(application.logger.handlers):
        handler.close()
        application.logger.removeHandler(handler)


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def log_text(flask_app):
    path = Path(flask_app.config["LOG_FILE"])

    def _read():
        for handler in flask_app.logger.handlers:
            handler.flush()
        return path.read_text(encoding="utf-8") if path.exists() else ""

    return _read


@pytest.fixture
def signup(flask_app):
    def _signup(name="Ali Raza", email=None, password="Bus12345", phone="+923001234567"):
        email = email or f"{uuid.uuid4().hex[:10]}@example.com"
        c = flask_app.test_client()
        r = c.post("/api/register", json={"full_name": name, "email": email,
                                          "password": password, "phone": phone})
        assert r.status_code == 201, r.get_json()
        r = c.post("/api/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.get_json()
        return c

    return _signup


@pytest.fixture
def conductor(flask_app, conn):
    email = "conductor@example.com"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, 'conductor')",
            ("Bilal Ahmed", email, hash_password("Conduct123")),
        )
    conn.commit()
    c = flask_app.test_client()
    r = c.post("/api/login", json={"email": email, "password": "Conduct123"})
    assert r.status_code == 200, r.get_json()
    return c