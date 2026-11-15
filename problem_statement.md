# Cloud-Based Bus Pass System: Problem Statement

CodeAlpha Cloud Computing Internship, Task 3.
Intern: Muhammad Akram (CA/DF1/323730).

## Requirements mapped to code

| CodeAlpha requirement | Our solution | Code |
|---|---|---|
| Online ticket booking hosted on cloud | Flask app on AWS EC2 with RDS MySQL | app/routes.py, wsgi.py |
| Ticket loss prevention | Every booking saved in DB, "My tickets" page | sql/schema.sql, app/booking.py |
| Ticket theft / forgery | HMAC signed ticket code tied to the passenger, validated once by conductor endpoint | app/security.py |
| Incorrect pricing prevention | Price calculated only on server from a fare table, stored with booking | app/pricing.py |
| No overselling | DB transaction with row lock, concurrency test | app/booking.py |
| High traffic, dynamic servers | Stateless app, Auto Scaling Group behind Application Load Balancer | AWS, /health route |
| Scalability and reliability | Health checks, RDS, load test script | tests/ |
| Test and deploy | pytest suite and AWS deployment | tests/, docs |

## Security rules

1. The client never sends a price.
2. Every SQL query uses prepared statements.
3. Passwords are hashed with bcrypt.
4. Ticket code is signed with HMAC and compared in constant time.
5. A ticket can be validated only once.
6. Real errors go to app.log, the client only sees "Server error".

## Out of scope

Online payment gateway, QR images, SMS and email notifications.