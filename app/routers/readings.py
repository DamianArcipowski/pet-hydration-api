from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from database import get_cursor, get_db
from security import MAC_REGEX, assert_device_owner, current_user_id

router = APIRouter(tags=["readings"])


def sum_drops(weights, threshold=3.0):
    total = sum(
        prev - cur for prev, cur in zip(weights, weights[1:]) if prev - cur > threshold
    )
    return round(total)


def daily_buckets(rows, days):
    grouped = defaultdict(list)
    for r in rows:
        grouped[str(r["day"])].append(r["weight_g"])
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    return [
        {"label": d.strftime("%d.%m"), "value": sum_drops(grouped.get(str(d), []))}
        for d in dates
    ]


@router.post("/readings", status_code=204)
async def post_reading(request: Request, x_device_mac=Header(..., alias="x-device-mac")):
    mac = x_device_mac.upper().strip()
    if not MAC_REGEX.match(mac):
        raise HTTPException(status_code=400, detail="Invalid MAC address")
    try:
        body = await request.json()
    except Exception:
        body = {}
    ssid = str(body.get("ssid") or "").strip()[:64]

    with get_db() as conn, get_cursor(conn) as cur:
        cur.execute("SELECT id FROM devices WHERE mac_address = %s", (mac,))
        device = cur.fetchone()
        if device is None:
            cur.execute("INSERT IGNORE INTO pending_devices (mac_address) VALUES (%s)", (mac,))
            return

        cur.execute(
            "INSERT INTO readings (device_id, weight_g, valve_open, tank_low, calibrated) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                device["id"],
                body.get("weight_g", 0),
                body.get("valve_open", 0),
                body.get("tank_low", 0),
                body.get("calibrated", 0),
            ),
        )
        if ssid:
            cur.execute(
                "UPDATE devices SET wifi_ssid = %s "
                "WHERE id = %s AND (wifi_ssid IS NULL OR wifi_ssid <> %s)",
                (ssid, device["id"], ssid),
            )


@router.get("/devices/{device_id}/readings/latest")
def get_latest_reading(device_id: int, user_id: int = Depends(current_user_id)):
    assert_device_owner(device_id, user_id)
    with get_db() as conn, get_cursor(conn) as cur:
        cur.execute(
            "SELECT id, device_id, weight_g, valve_open, tank_low, calibrated, recorded_at "
            "FROM readings WHERE device_id = %s ORDER BY recorded_at DESC LIMIT 1",
            (device_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No readings yet")
    return {**row, "recorded_at": str(row["recorded_at"])}


@router.get("/devices/{device_id}/readings/intake/today")
def get_today_intake(device_id: int):
    with get_db() as conn, get_cursor(conn) as cur:
        cur.execute(
            "SELECT weight_g FROM readings "
            "WHERE device_id = %s AND DATE(recorded_at) = CURDATE() AND calibrated = 1 "
            "ORDER BY recorded_at ASC",
            (device_id,),
        )
        rows = cur.fetchall()
    return {"total_ml": sum_drops([r["weight_g"] for r in rows])}


@router.get("/devices/{device_id}/readings/intake")
def get_intake(device_id: int, period: str = Query("day")):
    with get_db() as conn, get_cursor(conn) as cur:
        if period == "day":
            cur.execute(
                "SELECT HOUR(recorded_at) AS bucket, weight_g FROM readings "
                "WHERE device_id = %s AND DATE(recorded_at) = CURDATE() AND calibrated = 1 "
                "ORDER BY recorded_at ASC",
                (device_id,),
            )
            buckets = {h: [] for h in range(24)}
            for r in cur.fetchall():
                buckets[r["bucket"]].append(r["weight_g"])
            data = [{"label": f"{h:02d}:00", "value": sum_drops(buckets[h])} for h in range(24)]
        elif period in ("week", "month"):
            days = 7 if period == "week" else 30
            cur.execute(
                "SELECT DATE(recorded_at) AS day, weight_g FROM readings "
                "WHERE device_id = %s AND recorded_at >= CURDATE() - INTERVAL %s DAY "
                "AND calibrated = 1 ORDER BY recorded_at ASC",
                (device_id, days - 1),
            )
            data = daily_buckets(cur.fetchall(), days)

    total = sum(d["value"] for d in data)
    return {"period": period, "total": round(total), "data": data}