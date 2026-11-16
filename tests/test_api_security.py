import time

SQLI = [
    "' OR '1'='1",
    "1' UNION SELECT password_hash FROM users--",
    "admin'--",
    "1; DROP TABLE bookings;--",
    "1' AND SLEEP(5)--",
    "' OR 1=1 #",
]


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_health_503_when_database_is_down(client, monkeypatch, log_text):
    def broken():
        raise RuntimeError("db down")

    monkeypatch.setattr("app.routes.get_db", broken)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.get_json() == {"status": "error"}
    assert "Health check failed" in log_text()


def test_server_error_is_generic_for_client_but_logged(flask_app, client, log_text):
    @flask_app.get("/boom")
    def boom():
        raise RuntimeError("secret-detail-xyz")

    r = client.get("/boom")
    assert r.status_code == 500
    assert r.get_json() == {"error": "Server error"}
    text = r.get_data(as_text=True)
    assert "secret-detail-xyz" not in text
    assert "Traceback" not in text
    logged = log_text()
    assert "RuntimeError" in logged
    assert "secret-detail-xyz" in logged
    assert "Traceback" in logged


def test_unknown_path_and_wrong_method_are_json(client):
    r = client.get("/api/nothing-here")
    assert r.status_code == 404
    assert r.get_json() == {"error": "Not found"}
    assert client.get("/api/register").status_code == 405


def test_security_headers(client):
    r = client.get("/api/fares")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_sql_injection_in_login(client, signup):
    signup(email="victim@example.com")
    for p in SQLI:
        r = client.post("/api/login", json={"email": p, "password": "Bus12345"})
        assert r.status_code in (400, 401)
        r = client.post("/api/login", json={"email": "victim@example.com", "password": p})
        assert r.status_code == 401
    assert client.get("/api/me").status_code == 401


def test_sql_injection_in_register(client, conn):
    for p in SQLI:
        base = {"full_name": "Ali Raza", "email": "ali@example.com", "password": "Bus12345"}
        for field, value in (("full_name", p), ("email", p + "@x.com"), ("phone", p)):
            r = client.post("/api/register", json={**base, field: value})
            assert r.status_code == 400
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users")
        assert cur.fetchone()["n"] == 0
    conn.commit()


def test_sql_injection_in_booking_fields(signup, booking_count):
    from datetime import date, timedelta

    c = signup()
    travel = (date.today() + timedelta(days=1)).isoformat()
    base = {"route": "KHI-01", "pass_type": "weekly", "concession": "none",
            "travel_date": travel, "idempotency_key": "key-sqli-0001"}
    for field in base:
        for p in SQLI:
            r = c.post("/api/bookings", json={**base, field: p})
            assert r.status_code == 400, (field, p)
    assert booking_count() == 0
    assert c.get("/api/bookings").status_code == 200


def test_sql_injection_in_conductor_ticket(conductor):
    for p in SQLI:
        r = conductor.post("/api/conductor/validate", json={"ticket_code": p})
        assert r.status_code == 400


def test_time_based_payload_does_not_slow_the_server(client):
    start = time.perf_counter()
    for _ in range(3):
        client.post("/api/login", json={"email": "1' AND SLEEP(5)--@x.com", "password": "1' AND SLEEP(5)--"})
    assert time.perf_counter() - start < 3