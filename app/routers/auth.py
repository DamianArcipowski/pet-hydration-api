import hashlib
import hmac
import secrets
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from database import get_db, get_cursor
from security import (
    EMAIL_REGEX, current_user_id, hash_password, new_token, token_from_header, verify_password,
)
from mailer import send_email

router = APIRouter(prefix="/auth", tags=["auth"])

PASSWORD_MIN_LEN = 8
RESET_CODE_MINUTES  = 15
RESET_MAX_ATTEMPTS  = 5


async def read_credentials(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    return email, password


def create_session(cur, user_id: int = Depends(current_user_id)):
    token = new_token()
    cur.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, user_id))
    return token


def code_hash(user_id, code):
    return hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()


@router.post("/register", status_code=201)
async def register(request: Request):
    email, password = await read_credentials(request)

    if not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="Invalid email")
    if len(password) < PASSWORD_MIN_LEN:
        raise HTTPException(status_code=400, detail=f"Password must have at least {PASSWORD_MIN_LEN} characters")

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Email already registered")

            cur.execute(
                "INSERT INTO users (email, password) VALUES (%s, %s)",
                (email, hash_password(password)),
            )
            user_id = cur.lastrowid
            token = create_session(cur, user_id)
    return {"token": token, "user": {"id": user_id, "email": email}}


@router.post("/login")
async def login(request: Request):
    email, password = await read_credentials(request)

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id, password FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user or not verify_password(password, user["password"]):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            token = create_session(cur, user["id"])
    return {"token": token, "user": {"id": user["id"], "email": email}}


@router.post("/logout", status_code=204)
def logout(authorization: str = Header("")):
    token = token_from_header(authorization)
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("DELETE FROM sessions WHERE token = %s", (token,))


@router.get("/me")
def me(user_id: int = Depends(current_user_id)):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": row["id"], "email": row["email"]}


@router.post("/password/forgot", status_code=204)
async def forgot_password(request: Request):
    email, _ = await read_credentials(request)

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                return

            code = f"{secrets.randbelow(1_000_000):06d}"
            cur.execute(
                "REPLACE INTO password_resets (user_id, code_hash, expires_at, attempts) "
                "VALUES (%s, %s, UTC_TIMESTAMP() + INTERVAL %s MINUTE, 0)",
                (user["id"], code_hash(user["id"], code), RESET_CODE_MINUTES),
            )
    try:
        send_email(
            email,
            "Pet Hydration System - kod resetu hasła",
            f"Twój kod resetu hasła: {code}\n\n"
            f"Kod jest ważny przez {RESET_CODE_MINUTES} minut.\n"
            "Jeśli to nie Ty prosiłeś o reset, zignoruj tę wiadomość.",
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Could not send e-mail")


@router.post("/password/reset")
async def reset_password(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    email    = str(body.get("email", "")).strip().lower()
    code     = str(body.get("code", "")).strip()
    password = str(body.get("password", ""))

    if len(password) < PASSWORD_MIN_LEN:
        raise HTTPException(status_code=400, detail=f"Password must have at least {PASSWORD_MIN_LEN} characters")

    error = None
    token = None
    user_id = None

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            reset = None
            if user:
                user_id = user["id"]
                cur.execute(
                    "SELECT code_hash, attempts FROM password_resets "
                    "WHERE user_id = %s AND expires_at > UTC_TIMESTAMP()",
                    (user_id,),
                )
                reset = cur.fetchone()

            if not reset:
                error = "Invalid or expired code"
            elif reset["attempts"] >= RESET_MAX_ATTEMPTS:
                cur.execute("DELETE FROM password_resets WHERE user_id = %s", (user_id,))
                error = "Too many attempts"
            elif not hmac.compare_digest(reset["code_hash"], code_hash(user_id, code)):
                cur.execute(
                    "UPDATE password_resets SET attempts = attempts + 1 WHERE user_id = %s",
                    (user_id,),
                )
                error = "Invalid or expired code"
            else:
                cur.execute("UPDATE users SET password = %s WHERE id = %s", (hash_password(password), user_id))
                cur.execute("DELETE FROM password_resets WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
                token = create_session(cur, user_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"token": token, "user": {"id": user_id, "email": email}}
