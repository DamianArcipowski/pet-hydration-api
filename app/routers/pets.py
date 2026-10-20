from fastapi import APIRouter, HTTPException, Request, Query
from database import get_db, get_cursor

router = APIRouter(tags=["pets"])

@router.post("/devices/{device_id}/pet", status_code=201)
async def create_pet(device_id: int, request: Request, user_id: int = Query(0)):
    body = await request.json()
    name = body.get("name", "").strip()
    weight_kg = body.get("weight_kg", None)

    if not name:
        raise HTTPException(status_code=400, detail="Pet name is required")
    
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM devices WHERE id = %s AND user_id = %s", (device_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Device not found")

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
            row = cur.fetchone()
            return {"id": row["id"], "device_id": row["device_id"], "name": row["name"], "weight_kg": weight_kg}

@router.get("/devices/{device_id}/pet")
def get_pet(device_id: int, user_id: int = Query(0)):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM devices WHERE id = %s AND user_id = %s", (device_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Device not found")

            cur.execute(
                "SELECT d.id, d.device_id, d.name, "
                "       (SELECT weight_kg FROM pet_weight_log WHERE pet_id = d.id "
                "        ORDER BY measured_at DESC LIMIT 1) AS weight_kg "
                "FROM pets d WHERE d.device_id = %s",
                (device_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No pet profile yet")
            return {
                "id":        row["id"],
                "device_id": row["device_id"],
                "name":      row["name"],
                "weight_kg": row["weight_kg"],
            }
            
@router.post("/devices/{device_id}/pet/weight", status_code=201)
async def add_pet_weight(device_id: int, request: Request, user_id: int = Query(0)):
    body = await request.json()
    weight_kg = body.get("weight_kg")

    if weight_kg is None or float(weight_kg) <= 0:
        raise HTTPException(status_code=400, detail="weight_kg must be > 0")

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM devices WHERE id = %s AND user_id = %s", (device_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Device not found")

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
