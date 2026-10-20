import re
import json
from fastapi import APIRouter, HTTPException, Header, Request, Query
from database import get_db, get_cursor

router = APIRouter(tags=["readings"])

MAC_REGEX = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

@router.post("/readings", status_code=204)
async def post_reading(request: Request, x_device_mac=Header(..., alias="x-device-mac")):
    mac = x_device_mac.upper().strip()
    if not MAC_REGEX.match(mac):
        raise HTTPException(status_code=400, detail="Invalid MAC address")

    raw_body = await request.body()
    try:
        body = json.loads(raw_body) if raw_body else {}
    except Exception:
        body = {}

    weight_g = body.get("weight_g", 0)
    valve_open = body.get("valve_open", 0)
    tank_low = body.get("tank_low", 0)

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT id FROM devices WHERE mac_address = %s", (mac,))
            device = cur.fetchone()

            if device is None:
                cur.execute(
                    "INSERT IGNORE INTO pending_devices (mac_address) VALUES (%s)",
                    (mac,),
                )
                return

            device_id = device["id"]
            cur.execute(
                "INSERT INTO readings (device_id, weight_g, valve_open, tank_low) "
                "VALUES (%s, %s, %s, %s)",
                (device_id, weight_g, valve_open, tank_low),
            )

@router.get("/devices/{device_id}/readings/latest")
def get_latest_reading(device_id: int):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                "SELECT id, device_id, weight_g, valve_open, tank_low, recorded_at "
                "FROM readings WHERE device_id = %s ORDER BY recorded_at DESC LIMIT 1",
                (device_id,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No readings yet")
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "weight_g": row["weight_g"],
        "valve_open": row["valve_open"],
        "tank_low": row["tank_low"],
        "recorded_at": str(row["recorded_at"]),
    }

@router.get("/devices/{device_id}/readings/intake/today")
def get_today_intake(device_id: int):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                "SELECT weight_g FROM readings "
                "WHERE device_id = %s AND DATE(recorded_at) = CURDATE() "
                "ORDER BY recorded_at ASC",
                (device_id,),
            )
            rows = cur.fetchall()

    if len(rows) < 2:
        return {"total_ml": 0}

    total = 0.0
    for i in range(1, len(rows)):
        diff = rows[i - 1]["weight_g"] - rows[i]["weight_g"]
        if diff > 3.0:
            total += diff

    return {"total_ml": round(total)}