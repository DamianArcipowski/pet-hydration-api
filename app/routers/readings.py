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
    calibrated = body.get("calibrated", 0)

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
                "INSERT INTO readings (device_id, weight_g, valve_open, tank_low, calibrated) "
                "VALUES (%s, %s, %s, %s, %s)",
                (device_id, weight_g, valve_open, tank_low, calibrated),
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
                "WHERE device_id = %s AND DATE(recorded_at) = CURDATE() AND calibrated = 1 "
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

@router.get("/devices/{device_id}/readings/intake")
def get_intake(device_id: int, period: str = Query("day")):
    with get_db() as conn:
        with get_cursor(conn) as cur:
            if period == "day":
                cur.execute(
                    "SELECT HOUR(recorded_at) AS bucket, weight_g "
                    "FROM readings "
                    "WHERE device_id = %s AND DATE(recorded_at) = CURDATE() AND calibrated = 1 "
                    "ORDER BY recorded_at ASC",
                    (device_id,),
                )
                rows = cur.fetchall()
                buckets = {h: [] for h in range(24)}
                for r in rows:
                    buckets[r["bucket"]].append(r["weight_g"])
                data = []
                for h in range(24):
                    data.append({"label": f"{h:02d}:00", "value": sum_drops(buckets[h])})

            elif period == "week":
                cur.execute(
                    "SELECT DATE(recorded_at) AS day, weight_g "
                    "FROM readings "
                    "WHERE device_id = %s AND recorded_at >= CURDATE() - INTERVAL 6 DAY AND calibrated = 1 "
                    "ORDER BY recorded_at ASC",
                    (device_id,),
                )
                data = daily_buckets(cur.fetchall(), days=7)

            elif period == "month":
                cur.execute(
                    "SELECT DATE(recorded_at) AS day, weight_g "
                    "FROM readings "
                    "WHERE device_id = %s AND recorded_at >= CURDATE() - INTERVAL 29 DAY AND calibrated = 1 "
                    "ORDER BY recorded_at ASC",
                    (device_id,),
                )
                data = daily_buckets(cur.fetchall(), days=30)

    total = sum(d["value"] for d in data)
    return {"period": period, "total": round(total), "data": data}


def sum_drops(weights, threshold=3.0):
    total = 0.0
    for i in range(1, len(weights)):
        diff = weights[i - 1] - weights[i]
        if diff > threshold:
            total += diff
    return round(total)


def daily_buckets(rows, days):
    from datetime import date, timedelta
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in rows:
        grouped[str(r["day"])].append(r["weight_g"])
    today = date.today()
    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        result.append({"label": d.strftime("%d.%m"), "value": sum_drops(grouped.get(str(d), []))})
    return result