import time
from datetime import datetime, timedelta, timezone

import pymysql

from app.pricing import get_price
from app.security import TicketError, sign_ticket, verify_ticket

PKT = timezone(timedelta(hours=5))

_SELECT = (
    "SELECT b.id, b.pass_type, b.concession_code, b.travel_date, b.valid_until, "
    "b.price_pkr, b.ticket_code, b.status, r.code AS route_code, r.origin, r.destination "
    "FROM bookings b JOIN routes r ON r.id = b.route_id "
)


class SoldOutError(Exception):
    pass


class TicketUsedError(Exception):
    pass


def _public(row):
    return {
        "id": row["id"],
        "route_code": row["route_code"],
        "origin": row["origin"],
        "destination": row["destination"],
        "pass_type": row["pass_type"],
        "concession": row["concession_code"],
        "travel_date": row["travel_date"].isoformat(),
        "valid_until": row["valid_until"].isoformat(),
        "price_pkr": row["price_pkr"],
        "ticket_code": row["ticket_code"],
        "status": row["status"],
    }


def _expiry_epoch(valid_until):
    end = datetime.combine(valid_until + timedelta(days=1), datetime.min.time(), tzinfo=PKT)
    return int(end.timestamp())


def _find_by_key(conn, user_id, idempotency_key):
    with conn.cursor() as cur:
        cur.execute(
            _SELECT + "WHERE b.user_id = %s AND b.idempotency_key = %s",
            (user_id, idempotency_key),
        )
        row = cur.fetchone()
    return _public(row) if row else None


def _reserve(conn, user_id, quote, pass_type, concession, travel_date, idempotency_key, signing_key):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sold FROM route_capacity WHERE route_id = %s AND travel_date = %s FOR UPDATE",
            (quote["route_id"], travel_date),
        )
        row = cur.fetchone()
        if row["sold"] >= quote["daily_capacity"]:
            raise SoldOutError("sold out")
        cur.execute(
            "UPDATE route_capacity SET sold = sold + 1 WHERE route_id = %s AND travel_date = %s",
            (quote["route_id"], travel_date),
        )
        valid_until = travel_date + timedelta(days=quote["duration_days"] - 1)
        cur.execute(
            "INSERT INTO bookings (user_id, route_id, pass_type, concession_code, travel_date, "
            "valid_until, price_pkr, idempotency_key) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, quote["route_id"], pass_type, concession, travel_date,
             valid_until, quote["price_pkr"], idempotency_key),
        )
        booking_id = cur.lastrowid
        code = sign_ticket(booking_id, user_id, _expiry_epoch(valid_until), signing_key)
        cur.execute("UPDATE bookings SET ticket_code = %s WHERE id = %s", (code, booking_id))
        cur.execute(_SELECT + "WHERE b.id = %s", (booking_id,))
        return _public(cur.fetchone())


def create_booking(conn, user_id, route_code, pass_type, concession, travel_date,
                   idempotency_key, signing_key):
    quote = get_price(conn, route_code, pass_type, concession)
    conn.commit()

    found = _find_by_key(conn, user_id, idempotency_key)
    conn.commit()
    if found:
        return found, False

    with conn.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO route_capacity (route_id, travel_date, sold) VALUES (%s, %s, 0)",
            (quote["route_id"], travel_date),
        )
    conn.commit()

    for attempt in range(3):
        try:
            booking = _reserve(conn, user_id, quote, pass_type, concession,
                               travel_date, idempotency_key, signing_key)
            conn.commit()
            return booking, True
        except pymysql.err.IntegrityError as exc:
            conn.rollback()
            if exc.args[0] == 1062:
                found = _find_by_key(conn, user_id, idempotency_key)
                conn.commit()
                if found:
                    return found, False
            raise
        except pymysql.err.OperationalError as exc:
            conn.rollback()
            if exc.args[0] == 1213 and attempt < 2:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
        except Exception:
            conn.rollback()
            raise


def list_bookings(conn, user_id):
    with conn.cursor() as cur:
        cur.execute(_SELECT + "WHERE b.user_id = %s ORDER BY b.id DESC", (user_id,))
        rows = cur.fetchall()
    conn.commit()
    return [_public(row) for row in rows]


def get_booking(conn, user_id, booking_id):
    with conn.cursor() as cur:
        cur.execute(_SELECT + "WHERE b.id = %s AND b.user_id = %s", (booking_id, user_id))
        row = cur.fetchone()
    conn.commit()
    return _public(row) if row else None


def validate_ticket(conn, code, signing_key, now=None):
    data = verify_ticket(code, signing_key, now=now)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bookings SET status = 'used', used_at = NOW() "
                "WHERE id = %s AND user_id = %s AND ticket_code = %s AND status = 'active'",
                (data["ticket_id"], data["user_id"], code),
            )
            if cur.rowcount == 1:
                cur.execute(_SELECT + "WHERE b.id = %s", (data["ticket_id"],))
                result = _public(cur.fetchone())
                conn.commit()
                return result
            cur.execute(
                "SELECT status FROM bookings WHERE id = %s AND user_id = %s AND ticket_code = %s",
                (data["ticket_id"], data["user_id"], code),
            )
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if row is None:
        raise TicketError("invalid ticket")
    if row["status"] == "used":
        raise TicketUsedError("ticket already used")
    raise TicketError("ticket is not valid")