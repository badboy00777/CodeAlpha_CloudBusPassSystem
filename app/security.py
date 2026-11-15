import hashlib
import hmac
import os
import re
import time

import bcrypt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TicketError(ValueError):
    pass


class CryptoError(ValueError):
    pass


_DIGITS = re.compile(r"[0-9]{1,15}")


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password, stored_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("ascii"))
    except (ValueError, AttributeError):
        return False


def _mac(payload, key):
    return hmac.new(key.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()


def sign_ticket(ticket_id, user_id, expires_at, key):
    payload = f"{int(ticket_id)}.{int(user_id)}.{int(expires_at)}"
    return f"{payload}.{_mac(payload, key)}"


def verify_ticket(code, key, now=None):
    if not isinstance(code, str) or len(code) > 200:
        raise TicketError("invalid ticket")
    parts = code.split(".")
    if len(parts) != 4:
        raise TicketError("invalid ticket")
    ticket_id, user_id, expires_at, sig = parts
    for number in (ticket_id, user_id, expires_at):
        if not _DIGITS.fullmatch(number):
            raise TicketError("invalid ticket")
    expected = _mac(f"{ticket_id}.{user_id}.{expires_at}", key)
    if not hmac.compare_digest(expected.encode("ascii"), sig.encode("utf-8")):
        raise TicketError("invalid ticket")
    current = int(now if now is not None else time.time())
    if int(expires_at) < current:
        raise TicketError("ticket expired")
    return {
        "ticket_id": int(ticket_id),
        "user_id": int(user_id),
        "expires_at": int(expires_at),
    }


def _aes(key_hex):
    try:
        key = bytes.fromhex(key_hex)
    except (ValueError, TypeError):
        raise CryptoError("bad key")
    if len(key) != 32:
        raise CryptoError("key must be 32 bytes")
    return AESGCM(key)


def encrypt_text(plain, key_hex):
    nonce = os.urandom(12)
    return nonce + _aes(key_hex).encrypt(nonce, plain.encode("utf-8"), None)


def decrypt_text(blob, key_hex):
    try:
        return _aes(key_hex).decrypt(blob[:12], blob[12:], None).decode("utf-8")
    except (InvalidTag, ValueError):
        raise CryptoError("cannot decrypt")