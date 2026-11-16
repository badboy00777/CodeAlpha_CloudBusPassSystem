from functools import wraps

import pymysql
from flask import Blueprint, abort, current_app, jsonify, render_template, request, session
from app.booking import (
    SoldOutError,
    TicketUsedError,
    create_booking,
    get_booking,
    list_bookings,
    validate_ticket,
)
from app.db import get_db
from app.pricing import PricingError, get_price
from app.security import TicketError, encrypt_text, hash_password, verify_password
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

bp = Blueprint("main", __name__)

_DUMMY_HASH = hash_password("Dummy12345")


@bp.app_errorhandler(ValidationError)
def handle_validation(exc):
    return jsonify(error=str(exc)), 400


@bp.app_errorhandler(PricingError)
def handle_pricing(exc):
    return jsonify(error=str(exc)), 400


@bp.app_errorhandler(SoldOutError)
def handle_sold_out(exc):
    return jsonify(error="Sold out for this date"), 409


@bp.before_request
def json_only_for_writes():
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.is_json:
        abort(415)


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("JSON object expected")
    return data


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Login required"), 401
        return view(*args, **kwargs)

    return wrapper


def conductor_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE id = %s", (session["user_id"],))
            row = cur.fetchone()
        conn.commit()
        if not row or row["role"] != "conductor":
            return jsonify(error="Conductor access only"), 403
        return view(*args, **kwargs)

    return wrapper
@bp.get("/")
def page_home():
    return render_template("index.html")


@bp.get("/login")
def page_login():
    return render_template("login.html")


@bp.get("/book")
def page_book():
    return render_template("book.html")


@bp.get("/tickets")
def page_tickets():
    return render_template("tickets.html")


@bp.get("/conductor")
def page_conductor():
    return render_template("conductor.html")


@bp.get("/health")
def health():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        conn.commit()
    except Exception:
        current_app.logger.exception("Health check failed: database unreachable")
        return jsonify(status="error"), 503
    return jsonify(status="ok")


@bp.post("/api/register")
def register():
    data = body()
    name = clean_name(data.get("full_name"))
    email = clean_email(data.get("email"))
    password = clean_password(data.get("password"))
    phone_enc = None
    phone = data.get("phone")
    if phone not in (None, ""):
        phone_enc = encrypt_text(clean_phone(phone), current_app.config["AES_KEY_HEX"])
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (full_name, email, password_hash, phone_enc) VALUES (%s, %s, %s, %s)",
                (name, email, hash_password(password), phone_enc),
            )
        conn.commit()
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        if exc.args[0] == 1062:
            return jsonify(error="Email already registered"), 409
        raise
    return jsonify(message="Registered"), 201


@bp.post("/api/login")
def login():
    data = body()
    email = clean_email(data.get("email"))
    password = data.get("password")
    if not isinstance(password, str) or not password or len(password.encode("utf-8")) > 72:
        raise ValidationError("password is invalid")
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, full_name, role, password_hash FROM users WHERE email = %s", (email,)
        )
        user = cur.fetchone()
    conn.commit()
    ok = verify_password(password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not ok:
        return jsonify(error="Invalid email or password"), 401
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True
    current_app.logger.info("Login ok user_id=%s", user["id"])
    return jsonify(user={"id": user["id"], "full_name": user["full_name"], "role": user["role"]})


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out")


@bp.get("/api/me")
@login_required
def me():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, full_name, email, role FROM users WHERE id = %s", (session["user_id"],)
        )
        user = cur.fetchone()
    conn.commit()
    if not user:
        session.clear()
        return jsonify(error="Login required"), 401
    return jsonify(user=user)


@bp.get("/api/fares")
def fares():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.code, r.origin, r.destination, f.pass_type, f.duration_days, f.price_pkr "
            "FROM routes r JOIN fares f ON f.route_id = r.id WHERE r.active = 1 "
            "ORDER BY r.code, f.duration_days"
        )
        rows = cur.fetchall()
        cur.execute("SELECT code, percent_off FROM concessions ORDER BY percent_off")
        concessions = cur.fetchall()
    conn.commit()
    routes = {}
    for row in rows:
        route = routes.setdefault(
            row["code"],
            {"code": row["code"], "origin": row["origin"], "destination": row["destination"], "fares": []},
        )
        route["fares"].append(
            {"pass_type": row["pass_type"], "duration_days": row["duration_days"], "price_pkr": row["price_pkr"]}
        )
    return jsonify(routes=list(routes.values()), concessions=concessions)


@bp.post("/api/quote")
@login_required
def quote():
    data = body()
    q = get_price(
        get_db(),
        clean_route_code(data.get("route")),
        clean_pass_type(data.get("pass_type")),
        clean_concession(data.get("concession")),
    )
    get_db().commit()
    return jsonify(
        quote={
            "base_price_pkr": q["base_price_pkr"],
            "percent_off": q["percent_off"],
            "price_pkr": q["price_pkr"],
            "duration_days": q["duration_days"],
        }
    )


@bp.post("/api/bookings")
@login_required
def book():
    data = body()
    booking, created = create_booking(
        get_db(),
        session["user_id"],
        clean_route_code(data.get("route")),
        clean_pass_type(data.get("pass_type")),
        clean_concession(data.get("concession")),
        clean_travel_date(data.get("travel_date")),
        clean_idempotency_key(data.get("idempotency_key")),
        current_app.config["TICKET_SIGNING_KEY"],
    )
    if created:
        current_app.logger.info(
            "Booking created id=%s user_id=%s price=%s", booking["id"], session["user_id"], booking["price_pkr"]
        )
    return jsonify(booking=booking), (201 if created else 200)


@bp.get("/api/bookings")
@login_required
def my_bookings():
    return jsonify(bookings=list_bookings(get_db(), session["user_id"]))


@bp.get("/api/bookings/<int:booking_id>")
@login_required
def one_booking(booking_id):
    booking = get_booking(get_db(), session["user_id"], booking_id)
    if booking is None:
        return jsonify(error="Not found"), 404
    return jsonify(booking=booking)


@bp.post("/api/conductor/validate")
@conductor_required
def conductor_validate():
    code = body().get("ticket_code")
    try:
        result = validate_ticket(get_db(), code, current_app.config["TICKET_SIGNING_KEY"])
    except TicketUsedError:
        current_app.logger.warning("Replay attempt on an already used ticket")
        return jsonify(valid=False, error="Ticket already used"), 409
    except TicketError:
        current_app.logger.warning("Invalid or forged ticket presented")
        return jsonify(valid=False, error="Invalid ticket"), 400
    return jsonify(valid=True, booking=result)