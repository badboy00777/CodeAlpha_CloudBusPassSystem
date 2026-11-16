import inspect
import time
from datetime import date, timedelta

import pytest

from app.booking import (
    SoldOutError,
    TicketUsedError,
    create_booking,
    get_booking,
    list_bookings,
    validate_ticket,
)
from app.security import TicketError, sign_ticket, verify_ticket

KEY = "unit-test-signing-key-not-a-real-secret"
TRAVEL = date.today() + timedelta(days=1)


def book(conn, user_id, key="key-00000001", route="KHI-01", pass_type="weekly",
         concession="none", travel=TRAVEL):
    return create_booking(conn, user_id, route, pass_type, concession, travel, key, KEY)


def set_capacity(conn, value, route="KHI-01"):
    with conn.cursor() as cur:
        cur.execute("UPDATE routes SET daily_capacity=%s WHERE code=%s", (value, route))
    conn.commit()


def test_booking_is_saved_with_server_price(conn, make_user, booking_count):
    uid = make_user()
    booking, created = book(conn, uid, concession="student")
    assert created is True
    assert booking["price_pkr"] == 400
    assert booking["status"] == "active"
    assert booking["valid_until"] == (TRAVEL + timedelta(days=6)).isoformat()
    assert booking_count() == 1


def test_booking_function_accepts_no_price_from_the_client():
    names = inspect.signature(create_booking).parameters
    assert not any("price" in name for name in names)


def test_ticket_code_is_signed_for_this_booking_and_user(conn, make_user):
    uid = make_user()
    booking, _ = book(conn, uid)
    data = verify_ticket(booking["ticket_code"], KEY)
    assert data["ticket_id"] == booking["id"]
    assert data["user_id"] == uid


def test_user_cannot_see_other_users_tickets(conn, make_user):
    a, b = make_user(), make_user()
    booking_a, _ = book(conn, a, key="key-aaaaaaaa")
    booking_b, _ = book(conn, b, key="key-bbbbbbbb")
    assert [x["id"] for x in list_bookings(conn, a)] == [booking_a["id"]]
    assert [x["id"] for x in list_bookings(conn, b)] == [booking_b["id"]]
    assert get_booking(conn, a, booking_b["id"]) is None
    assert get_booking(conn, b, booking_b["id"])["id"] == booking_b["id"]


def test_same_idempotency_key_gives_the_same_booking(conn, make_user, sold_count):
    uid = make_user()
    first, created_1 = book(conn, uid, key="key-double-click")
    second, created_2 = book(conn, uid, key="key-double-click")
    assert (created_1, created_2) == (True, False)
    assert first["id"] == second["id"]
    assert len(list_bookings(conn, uid)) == 1
    assert sold_count() == 1


def test_sold_out_raises_and_saves_nothing(conn, make_user, sold_count):
    set_capacity(conn, 2)
    users = [make_user() for _ in range(3)]
    book(conn, users[0], key="key-user-0000")
    book(conn, users[1], key="key-user-0001")
    with pytest.raises(SoldOutError):
        book(conn, users[2], key="key-user-0002")
    assert list_bookings(conn, users[2]) == []
    assert sold_count() == 2


def test_other_date_has_its_own_capacity(conn, make_user):
    set_capacity(conn, 1)
    a, b = make_user(), make_user()
    book(conn, a, key="key-date-0001")
    with pytest.raises(SoldOutError):
        book(conn, b, key="key-date-0002")
    other, created = book(conn, b, key="key-date-0003", travel=TRAVEL + timedelta(days=1))
    assert created is True


def test_conductor_validates_a_ticket_only_once(conn, make_user):
    uid = make_user()
    booking, _ = book(conn, uid)
    result = validate_ticket(conn, booking["ticket_code"], KEY)
    assert result["status"] == "used"
    with pytest.raises(TicketUsedError):
        validate_ticket(conn, booking["ticket_code"], KEY)


def test_forged_or_edited_ticket_is_rejected(conn, make_user):
    a, b = make_user(), make_user()
    booking, _ = book(conn, a)
    parts = booking["ticket_code"].split(".")
    parts[1] = str(b)
    with pytest.raises(TicketError):
        validate_ticket(conn, ".".join(parts), KEY)
    with pytest.raises(TicketError):
        validate_ticket(conn, booking["ticket_code"], "wrong-key")
    with pytest.raises(TicketError):
        validate_ticket(conn, "1.2.3.deadbeef", KEY)
    assert get_booking(conn, a, booking["id"])["status"] == "active"


def test_correctly_signed_ticket_missing_from_database_is_rejected(conn):
    code = sign_ticket(99999, 1, int(time.time()) + 3600, KEY)
    with pytest.raises(TicketError):
        validate_ticket(conn, code, KEY)


def test_expired_ticket_is_rejected(conn, make_user):
    uid = make_user()
    booking, _ = book(conn, uid)
    far_future = int(time.time()) + 86400 * 400
    with pytest.raises(TicketError):
        validate_ticket(conn, booking["ticket_code"], KEY, now=far_future)


def test_saved_price_does_not_change_when_fare_changes_later(conn, make_user):
    uid = make_user()
    booking, _ = book(conn, uid)
    assert booking["price_pkr"] == 800
    update = (
        "UPDATE fares SET price_pkr=%s WHERE pass_type='weekly' "
        "AND route_id=(SELECT id FROM routes WHERE code='KHI-01')"
    )
    try:
        with conn.cursor() as cur:
            cur.execute(update, (900,))
        conn.commit()
        assert list_bookings(conn, uid)[0]["price_pkr"] == 800
        second, _ = book(conn, uid, key="key-second-0001")
        assert second["price_pkr"] == 900
    finally:
        with conn.cursor() as cur:
            cur.execute(update, (800,))
        conn.commit()