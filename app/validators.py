import re
from datetime import date, datetime, timedelta


class ValidationError(ValueError):
    pass


PASS_TYPES = ("daily", "weekly", "monthly")
CONCESSIONS = ("none", "student", "senior")
MAX_ADVANCE_DAYS = 30

_NAME = re.compile(r"[A-Za-z]{1,40}(?:[ '-][A-Za-z]{1,40}){0,5}\.?")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,80}\.[A-Za-z]{2,10}")
_PHONE = re.compile(r"\+?[0-9]{10,14}")
_ROUTE = re.compile(r"[A-Z]{3}-[0-9]{2}")
_KEY = re.compile(r"[A-Za-z0-9-]{8,64}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _text(value, field):
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    return value.strip()


def clean_name(value):
    v = _text(value, "name")
    if len(v) < 2 or len(v) > 80 or not _NAME.fullmatch(v):
        raise ValidationError("name is invalid")
    return v


def clean_email(value):
    v = _text(value, "email")
    if not _EMAIL.fullmatch(v):
        raise ValidationError("email is invalid")
    return v.lower()


def clean_password(value):
    if not isinstance(value, str):
        raise ValidationError("password must be text")
    if len(value) < 8 or len(value.encode("utf-8")) > 72:
        raise ValidationError("password must be 8 to 72 characters")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
        raise ValidationError("password needs letters and numbers")
    return value


def clean_phone(value):
    v = _text(value, "phone")
    if not _PHONE.fullmatch(v):
        raise ValidationError("phone is invalid")
    return v


def clean_route_code(value):
    v = _text(value, "route")
    if not _ROUTE.fullmatch(v):
        raise ValidationError("route is invalid")
    return v


def clean_pass_type(value):
    v = _text(value, "pass_type")
    if v not in PASS_TYPES:
        raise ValidationError("pass_type is invalid")
    return v


def clean_concession(value):
    if value is None or value == "":
        return "none"
    v = _text(value, "concession")
    if v not in CONCESSIONS:
        raise ValidationError("concession is invalid")
    return v


def clean_travel_date(value, today=None):
    v = _text(value, "travel_date")
    if not _DATE.fullmatch(v):
        raise ValidationError("travel_date must be YYYY-MM-DD")
    try:
        d = datetime.strptime(v, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("travel_date is not a real date")
    today = today or date.today()
    if d < today or d > today + timedelta(days=MAX_ADVANCE_DAYS):
        raise ValidationError("travel_date is out of range")
    return d


def clean_idempotency_key(value):
    v = _text(value, "idempotency_key")
    if not _KEY.fullmatch(v):
        raise ValidationError("idempotency_key is invalid")
    return v