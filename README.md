# CodeAlpha_CloudBusPassSystem

Cloud-based bus pass booking system built for the CodeAlpha Cloud Computing Internship (Task 3).

Intern: Muhammad Akram (CA/DF1/323730)

## What it does

Passengers register, book a bus pass, and see their tickets again anytime. A conductor validates each ticket once.

| Problem | How it is solved |
|---|---|
| Ticket loss | Every booking is saved in MySQL and shown on the My tickets page |
| Ticket theft and forgery | HMAC-signed ticket code tied to the passenger, accepted once by the conductor endpoint |
| Incorrect pricing | The price is calculated only on the server from a fare table and saved with the booking |
| Overselling | Database transaction with a row lock on the capacity row |
| Double click | Idempotency key per booking attempt |
| High traffic | Stateless Flask app, ready for an AWS Auto Scaling group behind a load balancer |

## Tech stack

HTML, CSS, JavaScript, Python (Flask), PyMySQL, MySQL, gunicorn, bcrypt, cryptography (AES-256-GCM), pytest. Cloud: AWS EC2, RDS, Application Load Balancer, Auto Scaling.

## Security design

- Prepared statements for every SQL query
- Input validation on every field before it reaches the database
- Passwords hashed with bcrypt, phone numbers encrypted with AES-256-GCM
- Signed session cookie (HttpOnly, SameSite), no server-side session state
- JSON-only POST requests (CSRF protection)
- Content Security Policy, X-Frame-Options and nosniff headers
- Real errors go to app.log with a traceback, the client only sees "Server error"
- Output on pages is written with textContent, never innerHTML

## Run locally

1. Create the database: `cmd /c "mysql -u root < sql\schema.sql"`
2. Copy `.env.example` to `.env` and fill in the values
3. `python -m venv .venv` then activate it, then `pip install -r requirements.txt`
4. `python create_conductor.py` to create a conductor account
5. `python -m flask --app wsgi run --port 8000`

## Tests

```
pytest -q
```

Covers price tampering, forged and replayed tickets, overselling with simultaneous bookings, user isolation, SQL injection payloads, page safety and the /health route.

## Load test

```
python tools/loadtest.py http://127.0.0.1:8000 --mode light --workers 10 --seconds 10
```

`--mode cpu` sends wrong logins so every request runs bcrypt. It is used to raise CPU and trigger Auto Scaling.

## Cloud architecture

Internet, then an Application Load Balancer (HTTP), then an Auto Scaling group of EC2 instances running gunicorn on port 8000, then a private RDS MySQL database. Security groups chain: alb-sg, app-sg, rds-sg. The /health route is used for target group health checks.

## License

Educational project for the CodeAlpha internship.