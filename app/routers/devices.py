import re
from fastapi import APIRouter, HTTPException, Request, Query, Depends
from database import get_db, get_cursor
from security import current_user_id

router = APIRouter(tags=["devices"])

MAC_REGEX = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

@router.get("/devices")
def list_devices(user_id: int = Depends(current_user_id)):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                "SELECT id, mac_address, name, bowl_weight_g, bowl_capacity_ml, fill_target_pct, wifi_ssid "
                "FROM devices WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            rows = cur.fetchall()
    return [
        {
            "id": r["id"],
            "mac_address": r["mac_address"],
            "name": r["name"],
            "bowl_weight_g": r["bowl_weight_g"],
            "bowl_capacity_ml": r["bowl_capacity_ml"],
            "fill_target_pct": r["fill_target_pct"],
            "wifi_ssid": r["wifi_ssid"],
        }
        for r in rows
    ]

@router.get("/pending-devices")
def list_pending():
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute("SELECT mac_address, first_seen FROM pending_devices ORDER BY first_seen DESC")
            rows = cur.fetchall()
            return [{"mac_address": r["mac_address"], "first_seen": str(r["first_seen"])} for r in rows]


@router.post("/pending-devices/claim", status_code=201)
async def claim_pending(request: Request, user_id: int = Depends(current_user_id)):
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

@router.post("/devices/{device_id}/tare", status_code=204)
def tare_device(device_id: int, user_id: int = Depends(current_user_id)):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                "UPDATE devices SET pending_command = 'tare' WHERE id = %s AND user_id = %s",
                (device_id, user_id),
            )

@router.patch("/devices/{device_id}")
async def update_device(device_id: int, request: Request, user_id: int = Depends(current_user_id)):
    body = await request.json()
    allowed = {"name", "bowl_weight_g", "bowl_capacity_ml", "fill_target_pct", "wifi_ssid"}
    fields = {k: v for k, v in body.items() if k in allowed and v is not None}

    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update")

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [device_id, user_id]

    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute(f"UPDATE devices SET {set_clause} WHERE id = %s AND user_id = %s", values)
            cur.execute(
                "SELECT id, mac_address, name, bowl_weight_g, bowl_capacity_ml, fill_target_pct, wifi_ssid "
                "FROM devices WHERE id = %s",
                (device_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Device not found")
            return {
                "id": row["id"],
                "mac_address": row["mac_address"],
                "name": row["name"],
                "bowl_weight_g": row["bowl_weight_g"],
                "bowl_capacity_ml": row["bowl_capacity_ml"],
                "fill_target_pct": row["fill_target_pct"],
                "wifi_ssid": row["wifi_ssid"],
            }
            
@router.get("/devices/config")
def get_device_config(x_device_mac: str = Query(...), wifi_ssid: str = Query(None)):
    mac = x_device_mac.upper().strip()
    with get_db() as conn:
        with get_cursor(conn) as cur:
            if wifi_ssid:
                cur.execute(
                    "UPDATE devices SET wifi_ssid = %s WHERE mac_address = %s",
                    (wifi_ssid, mac),
                )
            cur.execute(
                "SELECT id, pending_command, bowl_weight_g, bowl_capacity_ml, fill_low_pct, fill_target_pct, calibration "
                "FROM devices WHERE mac_address = %s", (mac,))
            row = cur.fetchone()
            if not row:
                return {"command": None}

            command = row["pending_command"]
            if command:
                cur.execute("UPDATE devices SET pending_command = NULL WHERE id = %s", (row["id"],))

    return {
        "bowl_weight_g":    row["bowl_weight_g"],
        "bowl_capacity_ml": row["bowl_capacity_ml"],
        "fill_low_pct":     row["fill_low_pct"],
        "fill_target_pct":  row["fill_target_pct"],
        "calibration":      row["calibration"],
        "command":          command,
    }

@router.post("/devices/tare-result", status_code=204)
async def tare_result(request: Request, x_device_mac: str = Query(...)):
    mac = x_device_mac.upper().strip()
    body = await request.json()
    bowl_weight_g = body.get("bowl_weight_g", 0)
    with get_db() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                "UPDATE devices SET bowl_weight_g = %s WHERE mac_address = %s",
                (bowl_weight_g, mac),
            )
