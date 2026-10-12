import re
import json
from fastapi import APIRouter, HTTPException, Header, Request
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
