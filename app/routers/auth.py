from fastapi import APIRouter, Depends, Header, HTTPException, Request
from app.database import get_db, get_cursor
from app.security import (
    EMAIL_REGEX, current_user_id, hash_password, new_token, token_from_header, verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

PASSWORD_MIN_LEN = 8

async def read_credentials(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    return email, password

def _create_session(cur, user_id: int = Depends(current_user_id)):
    token = new_token()
    cur.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, user_id))
    return token

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
            token = _create_session(cur, user_id)
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
            token = _create_session(cur, user["id"])
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