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