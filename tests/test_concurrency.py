import threading
from collections import Counter
from datetime import date, timedelta

from app.booking import SoldOutError, TicketUsedError, create_booking, validate_ticket
from app.db import get_connection

KEY = "unit-test-signing-key-not-a-real-secret"
TRAVEL = date.today() + timedelta(days=1)


def run_parallel(count, job):
    barrier = threading.Barrier(count)
    results = [None] * count

    def worker(i):
        conn = None
        try:
            conn = get_connection()
            barrier.wait(timeout=15)
            results[i] = job(conn, i)
        except SoldOutError:
            results[i] = "sold_out"
        except TicketUsedError:
            results[i] = "used"
        except Exception as exc:
            results[i] = f"error: {exc!r}"
        finally:
            if conn is not None:
                conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_no_overselling_with_simultaneous_bookings(conn, make_user, sold_count, booking_count):
    with conn.cursor() as cur:
        cur.execute("UPDATE routes SET daily_capacity=5 WHERE code='KHI-01'")
    conn.commit()
    users = [make_user() for _ in range(20)]

    def job(c, i):
        create_booking(c, users[i], "KHI-01", "daily", "none", TRAVEL, f"key-race-{i:04d}", KEY)
        return "booked"

    results = run_parallel(20, job)
    assert Counter(results) == {"booked": 5, "sold_out": 15}
    assert sold_count() == 5
    assert booking_count() == 5


def test_double_click_creates_only_one_booking(conn, make_user, sold_count, booking_count):
    uid = make_user()

    def job(c, i):
        booking, _ = create_booking(c, uid, "KHI-01", "daily", "none", TRAVEL, "key-double-click", KEY)
        return booking["id"]

    results = run_parallel(8, job)
    assert len(set(results)) == 1
    assert isinstance(results[0], int)
    assert sold_count() == 1
    assert booking_count() == 1


def test_replayed_ticket_is_accepted_only_once(conn, make_user):
    uid = make_user()
    booking, _ = create_booking(conn, uid, "KHI-01", "daily", "none", TRAVEL, "key-replay-0001", KEY)

    def job(c, i):
        result = validate_ticket(c, booking["ticket_code"], KEY)
        return "valid" if result["status"] == "used" else "unexpected"

    results = run_parallel(10, job)
    assert Counter(results) == {"valid": 1, "used": 9}