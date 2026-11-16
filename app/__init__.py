import logging
from datetime import timedelta

from flask import Flask, jsonify, request, session
from werkzeug.exceptions import HTTPException

from app.config import Config
from app.db import close_db

HTTP_MESSAGES = {
    400: "Bad request",
    404: "Not found",
    405: "Method not allowed",
    413: "Request too large",
    415: "Unsupported media type",
}


def _setup_logging(app, log_file):
    for handler in list(app.logger.handlers):
        handler.close()
        app.logger.removeHandler(handler)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=Config.SECRET_KEY,
        TICKET_SIGNING_KEY=Config.TICKET_SIGNING_KEY,
        AES_KEY_HEX=Config.AES_KEY_HEX,
        LOG_FILE=Config.LOG_FILE,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=Config.COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    if not app.config["SECRET_KEY"] or not app.config["TICKET_SIGNING_KEY"]:
        raise RuntimeError("SECRET_KEY and TICKET_SIGNING_KEY must be set in .env")
    try:
        if len(bytes.fromhex(app.config["AES_KEY_HEX"])) != 32:
            raise ValueError
    except ValueError:
        raise RuntimeError("AES_KEY_HEX must be 64 hex characters")

    _setup_logging(app, app.config["LOG_FILE"])
    app.teardown_appcontext(close_db)

    from app.routes import bp

    app.register_blueprint(bp)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        if not exc.code or exc.code < 400:
            return exc
        return jsonify(error=HTTP_MESSAGES.get(exc.code, "Request failed")), exc.code

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        app.logger.error(
            "Unhandled exception on %s %s (user_id=%s)",
            request.method, request.path, session.get("user_id"),
            exc_info=exc,
        )
        return jsonify(error="Server error"), 500

    @app.after_request
    def add_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'"
        )
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app