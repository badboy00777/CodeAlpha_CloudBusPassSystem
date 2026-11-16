import pytest


def reg(**over):
    data = {"full_name": "Ali Raza", "email": "ali.raza@example.com",
            "password": "Bus12345", "phone": "+923001234567"}
    data.update(over)
    return data


def test_register_login_me_logout(client):
    assert client.post("/api/register", json=reg()).status_code == 201
    r = client.post("/api/login", json={"email": "Ali.Raza@Example.com", "password": "Bus12345"})
    assert r.status_code == 200
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["email"] == "ali.raza@example.com"
    assert me.get_json()["user"]["role"] == "passenger"
    assert client.post("/api/logout", json={}).status_code == 200
    assert client.get("/api/me").status_code == 401


def test_register_stores_hash_and_encrypted_phone(client, conn):
    client.post("/api/register", json=reg())
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash, phone_enc FROM users")
        row = cur.fetchone()
    conn.commit()
    assert row["password_hash"].startswith("$2")
    assert "Bus12345" not in row["password_hash"]
    assert row["phone_enc"] is not None
    assert b"923001234567" not in row["phone_enc"]


def test_register_cannot_choose_role(client, conn):
    r = client.post("/api/register", json=reg(role="conductor"))
    assert r.status_code == 201
    with conn.cursor() as cur:
        cur.execute("SELECT role FROM users")
        assert cur.fetchone()["role"] == "passenger"
    conn.commit()


def test_duplicate_email_is_rejected(client):
    assert client.post("/api/register", json=reg()).status_code == 201
    r = client.post("/api/register", json=reg(full_name="Another Person"))
    assert r.status_code == 409


@pytest.mark.parametrize(
    "over",
    [
        {"full_name": "A"},
        {"full_name": "Ali<script>"},
        {"email": "not-an-email"},
        {"password": "short1"},
        {"password": "onlyletters"},
        {"phone": "abc"},
        {"full_name": None},
    ],
)
def test_register_bad_input(client, over):
    assert client.post("/api/register", json=reg(**over)).status_code == 400


def test_login_errors_are_generic(client):
    client.post("/api/register", json=reg())
    wrong = client.post("/api/login", json={"email": "ali.raza@example.com", "password": "Wrong12345"})
    unknown = client.post("/api/login", json={"email": "nobody@example.com", "password": "Wrong12345"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json() == {"error": "Invalid email or password"}


def test_me_needs_login(client):
    assert client.get("/api/me").status_code == 401


def test_form_posts_are_refused_for_csrf_safety(client):
    r = client.post("/api/login", data={"email": "a@b.com", "password": "Bus12345"})
    assert r.status_code == 415


def test_broken_json_is_a_clean_400(client):
    r = client.post("/api/login", data="not json", content_type="application/json")
    assert r.status_code == 400