from datetime import date

import pytest

from app.validators import (
    ValidationError,
    clean_concession,
    clean_email,
    clean_idempotency_key,
    clean_name,
    clean_pass_type,
    clean_password,
    clean_phone,
    clean_route_code,
    clean_travel_date,
)

SQLI = [
    "' OR '1'='1",
    "1' UNION SELECT password_hash FROM users--",
    "admin'--",
    "1; DROP TABLE bookings;--",
    "1' AND SLEEP(5)--",
]


def test_name_ok():
    assert clean_name("  Ali Raza ") == "Ali Raza"


@pytest.mark.parametrize("bad", ["", "A", "Ali<script>", "1234", "x" * 100, None, 123] + SQLI)
def test_name_bad(bad):
    with pytest.raises(ValidationError):
        clean_name(bad)


def test_email_ok_and_lowercased():
    assert clean_email("Ali.Raza@Example.com") == "ali.raza@example.com"


@pytest.mark.parametrize("bad", ["ali@", "a b@x.com", "x@y", "", None] + [s + "@x.com" for s in SQLI])
def test_email_bad(bad):
    with pytest.raises(ValidationError):
        clean_email(bad)


def test_password_ok():
    assert clean_password("Bus12345") == "Bus12345"


@pytest.mark.parametrize("bad", ["short1", "onlyletters", "12345678", "a" * 80 + "1", None])
def test_password_bad(bad):
    with pytest.raises(ValidationError):
        clean_password(bad)


@pytest.mark.parametrize("good", ["+923001234567", "03001234567"])
def test_phone_ok(good):
    assert clean_phone(good) == good


@pytest.mark.parametrize("bad", ["abc", "0300-123", "", None] + SQLI)
def test_phone_bad(bad):
    with pytest.raises(ValidationError):
        clean_phone(bad)


def test_route_ok():
    assert clean_route_code("KHI-01") == "KHI-01"


@pytest.mark.parametrize("bad", ["khi-01", "KHI01", "KHI-1", None] + ["KHI-01" + s for s in SQLI])
def test_route_bad(bad):
    with pytest.raises(ValidationError):
        clean_route_code(bad)


@pytest.mark.parametrize("good", ["daily", "weekly", "monthly"])
def test_pass_type_ok(good):
    assert clean_pass_type(good) == good


@pytest.mark.parametrize("bad", ["yearly", "", None] + ["daily" + s for s in SQLI])
def test_pass_type_bad(bad):
    with pytest.raises(ValidationError):
        clean_pass_type(bad)


def test_concession_default_and_ok():
    assert clean_concession(None) == "none"
    assert clean_concession("student") == "student"


@pytest.mark.parametrize("bad", ["free", "student" + SQLI[0], 5])
def test_concession_bad(bad):
    with pytest.raises(ValidationError):
        clean_concession(bad)


TODAY = date(2026, 11, 15)


def test_date_ok():
    assert clean_travel_date("2026-11-20", today=TODAY) == date(2026, 11, 20)


@pytest.mark.parametrize(
    "bad",
    ["2026-11-14", "2026-12-30", "20-11-2026", "2026-02-30", "", None, "2026-11-20' OR 1=1"],
)
def test_date_bad(bad):
    with pytest.raises(ValidationError):
        clean_travel_date(bad, today=TODAY)


def test_key_ok():
    k = "3f2a9c1e-7b1d-4c55-9d6e-1a2b3c4d5e6f"
    assert clean_idempotency_key(k) == k


@pytest.mark.parametrize("bad", ["short", "a b c d e f g h", "x" * 65, None] + SQLI)
def test_key_bad(bad):
    with pytest.raises(ValidationError):
        clean_idempotency_key(bad)