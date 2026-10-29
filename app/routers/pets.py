from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from database import get_cursor, get_db
from security import assert_device_owner, current_user_id

router = APIRouter(tags=["pets"])

LATEST_WEIGHT_PER_BUCKET = (
    "SUBSTRING_INDEX(GROUP_CONCAT(weight_kg ORDER BY measured_at DESC), ',', 1) AS weight_kg"
)


@router.post("/devices/{device_id}/pet", status_code=201)
async def create_pet(device_id: int, request: Request, user_id: int = Depends(current_user_id)):
    assert_device_owner(device_id, user_id)
    body = await request.json()
    name = body.get("name", "").strip()
    weight_kg = body.get("weight_kg", None)
    if not name:
        raise HTTPException(status_code=400, detail="Pet name is required")

    with get_db() as conn, get_cursor(conn) as cur:
        cur.execute("SELECT id FROM pets WHERE device_id = %s", (device_id,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Device already has a pet profile")
        cur.execute("INSERT INTO pets (device_id, name) VALUES (%s, %s)", (device_id, name))
        pet_id = cur.lastrowid
        if weight_kg is not None:
            cur.execute(
                "INSERT INTO pet_weight_log (pet_id, weight_kg) VALUES (%s, %s)",
                (pet_id, weight_kg),
            )
        cur.execute("SELECT id, device_id, name FROM pets WHERE id = %s", (pet_id,))
        return {**cur.fetchone(), "weight_kg": weight_kg}


@router.get("/devices/{device_id}/pet")
def get_pet(device_id: int, user_id: int = Depends(current_user_id)):
    assert_device_owner(device_id, user_id)
    with get_db() as conn, get_cursor(conn) as cur:
        cur.execute(
            "SELECT p.id, p.device_id, p.name, "
            "(SELECT weight_kg FROM pet_weight_log WHERE pet_id = p.id "
            "ORDER BY measured_at DESC LIMIT 1) AS weight_kg "
            "FROM pets p WHERE p.device_id = %s",
            (device_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No pet profile yet")
        return row


@router.post("/devices/{device_id}/pet/weight", status_code=201)
async def add_pet_weight(device_id: int, request: Request,
                         user_id: int = Depends(current_user_id)):
    assert_device_owner(device_id, user_id)
    body = await request.json()
    weight_kg = body.get("weight_kg")
    if weight_kg is None or float(weight_kg) <= 0:
        raise HTTPException(status_code=400, detail="weight_kg must be > 0")

    with get_db() as conn, get_cursor(conn) as cur:
        cur.execute("SELECT id FROM pets WHERE device_id = %s", (device_id,))
        pet = cur.fetchone()
        if not pet:
            raise HTTPException(status_code=404, detail="No pet profile for this device")
        cur.execute(
            "INSERT INTO pet_weight_log (pet_id, weight_kg) VALUES (%s, %s)",
            (pet["id"], float(weight_kg)),
        )
        new_id = cur.lastrowid
    return {"id": new_id, "weight_kg": float(weight_kg)}


@router.get("/devices/{device_id}/pet/weight/history")
def get_pet_weight_history(device_id: int, period: str = Query("week"),
                           user_id: int = Depends(current_user_id)):
    assert_device_owner(device_id, user_id)
    with get_db() as conn, get_cursor(conn) as cur:
        cur.execute("SELECT id FROM pets WHERE device_id = %s", (device_id,))
        pet = cur.fetchone()
        if not pet:
            raise HTTPException(status_code=404, detail="No pet profile yet")

        if period == "day":
            cur.execute(
                f"SELECT HOUR(measured_at) AS bucket, {LATEST_WEIGHT_PER_BUCKET} "
                "FROM pet_weight_log WHERE pet_id = %s AND DATE(measured_at) = CURDATE() "
                "GROUP BY bucket ORDER BY bucket ASC",
                (pet["id"],),
            )
            buckets = {r["bucket"]: float(r["weight_kg"]) for r in cur.fetchall()}
            data = [{"label": f"{h:02d}:00", "value": buckets.get(h)} for h in range(24)]
        else:
            days = 7 if period == "week" else 30
            cur.execute(
                f"SELECT DATE(measured_at) AS day, {LATEST_WEIGHT_PER_BUCKET} "
                "FROM pet_weight_log WHERE pet_id = %s "
                "AND measured_at >= CURDATE() - INTERVAL %s DAY "
                "GROUP BY day ORDER BY day ASC",
                (pet["id"], days - 1),
            )
            by_day = {str(r["day"]): float(r["weight_kg"]) for r in cur.fetchall()}
            today = date.today()
            dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
            data = [{"label": d.strftime("%d.%m"), "value": by_day.get(str(d))} for d in dates]
    return {"period": period, "data": data}