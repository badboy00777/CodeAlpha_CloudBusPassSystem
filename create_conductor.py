import getpass
import sys

import pymysql

from app.db import get_connection
from app.security import hash_password
from app.validators import ValidationError, clean_email, clean_name, clean_password


def main():
    try:
        name = clean_name(input("Conductor full name: "))
        email = clean_email(input("Conductor email: "))
        password = clean_password(getpass.getpass("Password (hidden): "))
    except ValidationError as exc:
        print("Invalid input:", exc)
        return 1
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, 'conductor')",
                (name, email, hash_password(password)),
            )
        conn.commit()
    except pymysql.err.IntegrityError:
        print("This email already exists.")
        return 1
    finally:
        conn.close()
    print("Conductor created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())