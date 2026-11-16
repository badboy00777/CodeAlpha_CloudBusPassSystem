import pytest

from app.pricing import PricingError, compute_price, get_price


@pytest.mark.parametrize(
    "base,percent,expected",
    [(800, 50, 400), (150, 0, 150), (150, 30, 105), (2800, 50, 1400), (3500, 30, 2450), (1, 50, 1)],
)
def test_compute_price(base, percent, expected):
    assert compute_price(base, percent) == expected


@pytest.mark.parametrize(
    "base,percent",
    [(-1, 0), (100, -5), (100, 101), ("100", 0), (100, "10")],
)
def test_compute_price_rejects_bad_input(base, percent):
    with pytest.raises(PricingError):
        compute_price(base, percent)


def test_get_price_from_fare_table(conn):
    quote = get_price(conn, "KHI-01", "weekly", "none")
    assert quote["price_pkr"] == 800
    assert quote["duration_days"] == 7


def test_get_price_student_discount(conn):
    assert get_price(conn, "KHI-01", "weekly", "student")["price_pkr"] == 400


def test_get_price_senior_on_another_route(conn):
    assert get_price(conn, "KHI-02", "monthly", "senior")["price_pkr"] == 2450


@pytest.mark.parametrize(
    "route,pass_type,concession",
    [
        ("KHI-99", "weekly", "none"),
        ("KHI-01", "yearly", "none"),
        ("KHI-01", "weekly", "free"),
        ("KHI-01' OR '1'='1", "weekly", "none"),
    ],
)
def test_get_price_unknown_values_are_rejected(conn, route, pass_type, concession):
    with pytest.raises(PricingError):
        get_price(conn, route, pass_type, concession)


def test_price_always_follows_the_fare_table(conn):
    update = (
        "UPDATE fares SET price_pkr=%s WHERE pass_type='weekly' "
        "AND route_id=(SELECT id FROM routes WHERE code='KHI-01')"
    )
    try:
        with conn.cursor() as cur:
            cur.execute(update, (900,))
        conn.commit()
        assert get_price(conn, "KHI-01", "weekly", "none")["price_pkr"] == 900
    finally:
        with conn.cursor() as cur:
            cur.execute(update, (800,))
        conn.commit()