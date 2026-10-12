import re
from fastapi import APIRouter, HTTPException, Request, Query
from database import get_db, get_cursor

router = APIRouter(tags=["devices"])

MAC_REGEX = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

@router.get("/pending-devices")
def list_pending():
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT mac_address, first_seen FROM pending_devices ORDER BY first_seen DESC")
            rows = cur.fetchall()
            return [{"mac_address": r["mac_address"], "first_seen": str(r["first_seen"])} for r in rows]


@router.post("/pending-devices/claim", status_code=201)
async def claim_pending(request: Request, user_id=Query(0)):
    body = await request.json()
    mac = body.get("mac_address", "").upper().strip()
    name = body.get("name", "")

    if not MAC_REGEX.match(mac):
        raise HTTPException(status_code=400, detail="Invalid MAC address")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT mac_address FROM pending_devices WHERE mac_address = %s", (mac,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Pending device not found")

            cur.execute("SELECT id FROM devices WHERE mac_address = %s", (mac,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Device already registered")

            cur.execute(
                "INSERT INTO devices (mac_address, user_id, name) VALUES (%s, %s, %s)",
                (mac, user_id, name),
            )
            new_id = cur.lastrowid
            cur.execute("DELETE FROM pending_devices WHERE mac_address = %s", (mac,))

            cur.execute(
                "SELECT id, mac_address, name, bowl_weight_g, bowl_capacity_ml, "
                "fill_target_pct, wifi_ssid FROM devices WHERE id = %s",
                (new_id,),
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "mac_address": row["mac_address"],
                "name": row["name"],
                "bowl_weight_g": row["bowl_weight_g"],
                "bowl_capacity_ml": row["bowl_capacity_ml"],
                "fill_target_pct": row["fill_target_pct"],
                "wifi_ssid": row["wifi_ssid"],
            }
