import pytest

from app.security import (
    CryptoError,
    TicketError,
    decrypt_text,
    encrypt_text,
    hash_password,
    sign_ticket,
    verify_password,
    verify_ticket,
)

KEY = "unit-test-signing-key-not-a-real-secret"
AES = "ab" * 32
NOW = 1_800_000_000


def test_password_hash_and_verify():
    h = hash_password("Bus12345")
    assert h != "Bus12345"
    assert verify_password("Bus12345", h) is True
    assert verify_password("Wrong12345", h) is False


def test_password_hash_is_salted():
    assert hash_password("Bus12345") != hash_password("Bus12345")


def test_verify_password_bad_hash_is_false():
    assert verify_password("Bus12345", "not-a-bcrypt-hash") is False
    assert verify_password("Bus12345", None) is False


def test_ticket_roundtrip():
    code = sign_ticket(15, 7, NOW + 3600, KEY)
    assert verify_ticket(code, KEY, now=NOW) == {
        "ticket_id": 15,
        "user_id": 7,
        "expires_at": NOW + 3600,
    }


def _tamper(code, index, new_value):
    parts = code.split(".")
    parts[index] = new_value
    return ".".join(parts)


def test_ticket_edited_fields_are_rejected():
    code = sign_ticket(15, 7, NOW + 3600, KEY)
    forged = [
        _tamper(code, 0, "16"),
        _tamper(code, 1, "8"),
        _tamper(code, 2, str(NOW + 999999)),
        code[:-1] + ("0" if code[-1] != "0" else "1"),
    ]
    for f in forged:
        with pytest.raises(TicketError):
            verify_ticket(f, KEY, now=NOW)


def test_ticket_signed_with_other_key_is_rejected():
    code = sign_ticket(15, 7, NOW + 3600, "some-other-key")
    with pytest.raises(TicketError):
        verify_ticket(code, KEY, now=NOW)


def test_ticket_expired():
    code = sign_ticket(15, 7, NOW - 1, KEY)
    with pytest.raises(TicketError, match="expired"):
        verify_ticket(code, KEY, now=NOW)


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "abc",
        "1.2.3",
        "1.2.3.4.5",
        "a.b.c.d",
        "1.2.3.zz",
        "1' OR '1'='1.2.3.4",
        "1.2.3.4; DROP TABLE bookings;--",
        None,
        12345,
    ],
)
def test_ticket_garbage_is_rejected(garbage):
    with pytest.raises(TicketError):
        verify_ticket(garbage, KEY, now=NOW)


def test_aes_roundtrip():
    blob = encrypt_text("+923001234567", AES)
    assert b"923001234567" not in blob
    assert decrypt_text(blob, AES) == "+923001234567"


def test_aes_uses_new_nonce_each_time():
    assert encrypt_text("same", AES) != encrypt_text("same", AES)


def test_aes_tampered_data_is_rejected():
    blob = encrypt_text("secret", AES)
    bad = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(CryptoError):
        decrypt_text(bad, AES)


def test_aes_wrong_key_is_rejected():
    blob = encrypt_text("secret", AES)
    with pytest.raises(CryptoError):
        decrypt_text(blob, "cd" * 32)


def test_aes_bad_key_length():
    with pytest.raises(CryptoError):
        encrypt_text("x", "abcd")