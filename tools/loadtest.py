import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

MODES = ("light", "cpu")
MAX_WORKERS = 200
MAX_SECONDS = 600


def _build_request(base, mode):
    if mode == "cpu":
        data = json.dumps({"email": "loadtest@example.com", "password": "Wrong12345"}).encode("utf-8")
        return urllib.request.Request(
            base + "/api/login", data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
    return urllib.request.Request(base + "/api/fares")


def _hit(base, mode):
    request = _build_request(base, mode)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
    except Exception:
        return None, time.perf_counter() - start
    return status, time.perf_counter() - start


def run_load(base_url, mode="light", workers=10, seconds=10):
    if mode not in MODES:
        raise ValueError("mode must be light or cpu")
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be 1 to {MAX_WORKERS}")
    if not 0 < seconds <= MAX_SECONDS:
        raise ValueError(f"seconds must be more than 0 and at most {MAX_SECONDS}")

    base = base_url.rstrip("/")
    lock = threading.Lock()
    latencies = []
    statuses = Counter()
    errors = [0]
    started = time.perf_counter()
    deadline = started + seconds

    def worker():
        while time.perf_counter() < deadline:
            status, took = _hit(base, mode)
            with lock:
                latencies.append(took)
                if status is None or status >= 500:
                    errors[0] += 1
                if status is not None:
                    statuses[status] += 1
            if status is None:
                time.sleep(0.05)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    elapsed = max(time.perf_counter() - started, 0.001)
    ordered = sorted(latencies)
    total = len(ordered)

    def pct(p):
        if not ordered:
            return 0.0
        return ordered[min(total - 1, int(total * p))] * 1000

    return {
        "total": total,
        "errors": errors[0],
        "rps": total / elapsed,
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "max_ms": (ordered[-1] * 1000) if ordered else 0.0,
        "statuses": dict(statuses),
        "seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Small load test for our own bus pass app")
    parser.add_argument("url", help="for example http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=MODES, default="light")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    print(f"Load test: {args.url} mode={args.mode} workers={args.workers} seconds={args.seconds}")
    stats = run_load(args.url, args.mode, args.workers, args.seconds)
    print(f"Requests : {stats['total']}")
    print(f"Errors   : {stats['errors']}")
    print(f"Req/sec  : {stats['rps']:.1f}")
    print(f"Latency  : p50 {stats['p50_ms']:.0f} ms, p95 {stats['p95_ms']:.0f} ms, max {stats['max_ms']:.0f} ms")
    print(f"Statuses : {stats['statuses']}")
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())