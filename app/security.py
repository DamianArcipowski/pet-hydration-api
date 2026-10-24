import hashlib
import hmac
import re
import secrets
from fastapi import Header, HTTPException
from app.database import get_db, get_cursor

PBKDF2_ITERATIONS = 200_000
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"

def verify_password(password, stored):
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)

def new_token():
    return secrets.token_hex(32)

def token_from_header(authorization):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token.strip()

def current_user_id(authorization: str = Header("")):
    token = token_from_header(authorization)
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT user_id FROM sessions WHERE token = %s", (token,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return row["user_id"]

def assert_device_owner(device_id, user_id):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM devices WHERE id = %s AND user_id = %s", (device_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Device not found")