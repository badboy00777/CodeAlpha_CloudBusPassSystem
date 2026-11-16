import uuid
from datetime import date, timedelta

import pytest

TRAVEL = (date.today() + timedelta(days=1)).isoformat()


def payload(**over):
    data = {"route": "KHI-01", "pass_type": "weekly", "concession": "student",
            "travel_date": TRAVEL, "idempotency_key": uuid.uuid4().hex}
    data.update(over)
    return data


def test_fares_are_public(client):
    r = client.get("/api/fares")
    assert r.status_code == 200
    body = r.get_json()
    assert "KHI-01" in [x["code"] for x in body["routes"]]
    assert "student" in [x["code"] for x in body["concessions"]]


def test_quote_uses_server_fare(signup):
    c = signup()
    r = c.post("/api/quote", json={"route": "KHI-01", "pass_type": "weekly",
                                   "concession": "student", "price_pkr": 1})
    assert r.status_code == 200
    assert r.get_json()["quote"]["price_pkr"] == 400


def test_booking_needs_login(client):
    assert client.post("/api/bookings", json=payload()).status_code == 401


def test_booking_created(signup):
    c = signup()
    r = c.post("/api/bookings", json=payload())
    assert r.status_code == 201
    booking = r.get_json()["booking"]
    assert booking["price_pkr"] == 400
    assert booking["status"] == "active"
    assert booking["ticket_code"]


def test_price_sent_by_client_is_ignored(signup, conn):
    c = signup()
    r = c.post("/api/bookings", json=payload(concession="none", price_pkr=1, price=1,
                                             total=1, amount=1, fare=1))
    assert r.status_code == 201
    assert r.get_json()["booking"]["price_pkr"] == 800
    with conn.cursor() as cur:
        cur.execute("SELECT price_pkr FROM bookings")
        assert cur.fetchone()["price_pkr"] == 800
    conn.commit()


def test_double_click_gives_same_booking(signup):
    c = signup()
    data = payload()
    first = c.post("/api/bookings", json=data)
    second = c.post("/api/bookings", json=data)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.get_json()["booking"]["id"] == second.get_json()["booking"]["id"]
    assert len(c.get("/api/bookings").get_json()["bookings"]) == 1


@pytest.mark.parametrize(
    "over",
    [
        {"route": "KHI-99"},
        {"route": "khi-01"},
        {"pass_type": "yearly"},
        {"concession": "free"},
        {"travel_date": "2020-01-01"},
        {"travel_date": "not-a-date"},
        {"idempotency_key": "x"},
        {"idempotency_key": None},
    ],
)
def test_booking_bad_input(signup, over):
    c = signup()
    assert c.post("/api/bookings", json=payload(**over)).status_code == 400


def test_sold_out_returns_409(signup, conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE routes SET daily_capacity=1 WHERE code='KHI-01'")
    conn.commit()
    a, b = signup(), signup()
    assert a.post("/api/bookings", json=payload()).status_code == 201
    r = b.post("/api/bookings", json=payload())
    assert r.status_code == 409
    assert "Sold out" in r.get_json()["error"]


def test_user_cannot_see_other_users_tickets(signup):
    a, b = signup(), signup()
    booking = a.post("/api/bookings", json=payload()).get_json()["booking"]
    assert b.get("/api/bookings").get_json()["bookings"] == []
    assert b.get(f"/api/bookings/{booking['id']}").status_code == 404
    assert a.get(f"/api/bookings/{booking['id']}").status_code == 200


def test_ticket_survives_logout_and_new_login(client, flask_app):
    client.post("/api/register", json={"full_name": "Sana Khan", "email": "sana@example.com",
                                       "password": "Bus12345"})
    client.post("/api/login", json={"email": "sana@example.com", "password": "Bus12345"})
    booking = client.post("/api/bookings", json=payload()).get_json()["booking"]
    client.post("/api/logout", json={})
    other_device = flask_app.test_client()
    other_device.post("/api/login", json={"email": "sana@example.com", "password": "Bus12345"})
    tickets = other_device.get("/api/bookings").get_json()["bookings"]
    assert [t["id"] for t in tickets] == [booking["id"]]
    assert tickets[0]["ticket_code"] == booking["ticket_code"]


def test_conductor_validates_once_and_replay_fails(signup, conductor):
    code = signup().post("/api/bookings", json=payload()).get_json()["booking"]["ticket_code"]
    first = conductor.post("/api/conductor/validate", json={"ticket_code": code})
    assert first.status_code == 200
    assert first.get_json()["valid"] is True
    assert first.get_json()["booking"]["status"] == "used"
    replay = conductor.post("/api/conductor/validate", json={"ticket_code": code})
    assert replay.status_code == 409
    assert replay.get_json()["valid"] is False


def test_passenger_cannot_use_conductor_endpoint(signup):
    c = signup()
    code = c.post("/api/bookings", json=payload()).get_json()["booking"]["ticket_code"]
    assert c.post("/api/conductor/validate", json={"ticket_code": code}).status_code == 403


def test_conductor_endpoint_needs_login(client):
    assert client.post("/api/conductor/validate", json={"ticket_code": "x"}).status_code == 401


def test_forged_ticket_is_rejected_and_stays_active(signup, conductor):
    a, b = signup(), signup()
    booking = a.post("/api/bookings", json=payload()).get_json()["booking"]
    me_b = b.get("/api/me").get_json()["user"]["id"]
    parts = booking["ticket_code"].split(".")
    stolen = list(parts)
    stolen[1] = str(me_b)
    bad_sig = list(parts)
    bad_sig[3] = "0" * 64
    for forged in (".".join(stolen), ".".join(bad_sig)):
        r = conductor.post("/api/conductor/validate", json={"ticket_code": forged})
        assert r.status_code == 400
        assert r.get_json()["valid"] is False
    assert a.get(f"/api/bookings/{booking['id']}").get_json()["booking"]["status"] == "active"


@pytest.mark.parametrize("junk", ["", "abc", None, 123, "1.2.3.4", "1' OR '1'='1"])
def test_garbage_ticket_codes_are_rejected(conductor, junk):
    r = conductor.post("/api/conductor/validate", json={"ticket_code": junk})
    assert r.status_code == 400