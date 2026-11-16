from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
TEMPLATES = sorted((APP_DIR / "templates").glob("*.html"))
PAGES = ["/", "/login", "/book", "/tickets", "/conductor"]
FORBIDDEN = [
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "<script src",
    ' style="',
    "onclick=",
    "localStorage",
    "sessionStorage",
    "http://",
    "https://",
]


@pytest.mark.parametrize("path", PAGES)
def test_page_loads_with_the_single_stylesheet(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.content_type
    body = r.get_data(as_text=True)
    assert body.count('href="/static/style.css"') == 1
    assert "Cloud Bus Pass" in body
    assert "<script>" in body


@pytest.mark.parametrize("path", PAGES)
def test_pages_carry_security_headers(client, path):
    r = client.get(path)
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_six_templates_exist():
    names = [t.name for t in TEMPLATES]
    for expected in ("base.html", "index.html", "login.html", "book.html", "tickets.html", "conductor.html"):
        assert expected in names


@pytest.mark.parametrize("template", TEMPLATES, ids=[t.name for t in TEMPLATES])
def test_templates_have_no_dangerous_patterns(template):
    text = template.read_text(encoding="utf-8")
    assert len(text) > 200
    for bad in FORBIDDEN:
        assert bad not in text, f"{template.name} contains {bad}"


def test_only_one_css_file_and_no_javascript_files():
    files = sorted(p.name for p in (APP_DIR / "static").iterdir() if p.is_file())
    assert files == ["style.css"]


def test_css_is_served_and_loads_nothing_external(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert "text/css" in r.content_type
    css = r.get_data(as_text=True)
    assert len(css) > 1000
    assert "@import" not in css
    assert "http" not in css


def test_pages_open_without_login_but_data_stays_protected(client):
    assert client.get("/book").status_code == 200
    assert client.get("/tickets").status_code == 200
    assert client.get("/api/bookings").status_code == 401
    assert client.get("/api/me").status_code == 401