from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from flask import Flask, jsonify
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build


# Load environment variables from a .env file if present. This allows local
# development without passing a large number of environment variables via
# systemd. When running under systemd the EnvironmentFile option will supply
# the same variables so loading here is harmless.
load_dotenv(os.getenv("ROOM_KIOSK_ENV", "/opt/room-kiosk/.env"))

app = Flask(__name__)

# OAuth scope for read‑only calendar access. FreeBusy does not require full
# Calendar API scope but read‑only scope is safe and sufficient.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Required environment variables.  These are loaded from the .env file at
# service start. See `.env.example` in this directory for details.
DELEGATED_USER = os.environ["DELEGATED_USER"]
CREDS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "/opt/room-kiosk/creds.json")

# Two rooms are supported out of the box.  Each entry has a unique key
# (used by the front‑end) plus a human friendly name and the Google
# resource email/ID for the calendar.  To add more rooms simply append
# additional dictionary entries.
ROOMS = [
    {
        "key": "room04",
        "name": os.environ.get("ROOM_04_NAME", "0.4"),
        "calendar_id": os.environ["ROOM_04_CALENDAR_ID"],
    },
    {
        "key": "room05",
        "name": os.environ.get("ROOM_05_NAME", "0.5"),
        "calendar_id": os.environ["ROOM_05_CALENDAR_ID"],
    },
]

# How far into the future to look for upcoming bookings (hours) and how long
# cached results should be retained (seconds).  The caching ensures the Pi
# isn't constantly querying Google.
LOOKAHEAD_HOURS = int(os.environ.get("LOOKAHEAD_HOURS", "12"))
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "15"))

# Simple in‑memory cache.  Contains the timestamp of the last fetch and
# the payload returned to callers.
_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}


def iso_z(dt: datetime) -> str:
    """Return an RFC3339 timestamp in UTC with a Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def parse_rfc3339(s: str) -> datetime:
    """Parse RFC3339 timestamps returned by Google into timezone‑aware datetimes."""
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def get_calendar_service():
    """Create a Google Calendar API client using service account + delegation."""
    creds = service_account.Credentials.from_service_account_file(
        CREDS_PATH,
        scopes=SCOPES,
    )
    delegated = creds.with_subject(DELEGATED_USER)
    return build("calendar", "v3", credentials=delegated, cache_discovery=False)


def derive_state_from_busy(
    busy: List[Dict[str, str]], now: datetime
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Determine room state using FreeBusy ranges only (privacy safe).

    Returns:
      - state: "occupied" or "free"
      - current_end: RFC3339 Z if occupied
      - next_start: RFC3339 Z if there is a future busy slot
    """
    now_utc = now.astimezone(timezone.utc)

    current_end: Optional[datetime] = None
    next_start: Optional[datetime] = None

    ranges = sorted(
        [(parse_rfc3339(b["start"]), parse_rfc3339(b["end"])) for b in busy],
        key=lambda x: x[0],
    )

    for start, end in ranges:
        if start <= now_utc < end:
            current_end = end
            break

    if current_end is None:
        for start, _ in ranges:
            if start > now_utc:
                next_start = start
                break
        return "free", None, iso_z(next_start) if next_start else None

    for start, _ in ranges:
        if start >= current_end:
            next_start = start
            break

    return "occupied", iso_z(current_end), iso_z(next_start) if next_start else None


def fetch_status_payload() -> Dict[str, Any]:
    """Fetch FreeBusy data for all rooms and return a privacy‑safe status payload."""
    service = get_calendar_service()

    now = datetime.now(timezone.utc)
    time_min = now - timedelta(minutes=1)
    time_max = now + timedelta(hours=LOOKAHEAD_HOURS)

    items = [{"id": r["calendar_id"]} for r in ROOMS]

    body = {
        "timeMin": iso_z(time_min),
        "timeMax": iso_z(time_max),
        "items": items,
    }

    resp = service.freebusy().query(body=body).execute()
    calendars = resp.get("calendars", {})

    rooms_out: Dict[str, Any] = {}

    for r in ROOMS:
        cal = calendars.get(r["calendar_id"], {})
        busy = cal.get("busy", [])
        state, current_end, next_start = derive_state_from_busy(busy, now)

        rooms_out[r["key"]] = {
            "label": r["name"],
            "calendar_id": r["calendar_id"],
            "state": state,
            "current_end": current_end,
            "next_start": next_start,
            "updated_at": iso_z(now),
        }

    return {"rooms": rooms_out, "updated_at": iso_z(now)}


@app.get("/api/status")
def api_status():
    """Return room states in JSON. Uses in‑memory caching for performance."""
    now_ts = time.time()

    if _cache["payload"] is not None and (now_ts - _cache["ts"]) < CACHE_SECONDS:
        return jsonify(_cache["payload"])

    try:
        payload = fetch_status_payload()
        _cache["payload"] = payload
        _cache["ts"] = now_ts
        return jsonify(payload)
    except Exception as e:
        # Log full error details to journald for debugging
        app.logger.exception("Failed to fetch room status from Google Calendar FreeBusy")

        # Keep last known good payload if we have one
        if _cache["payload"] is not None:
            cached = dict(_cache["payload"])
            cached["warning"] = f"Using cached data due to backend error: {type(e).__name__}: {e}"
            return jsonify(cached), 200

        # Otherwise return an error with message for troubleshooting (local only)
        return jsonify(
            {
                "error": "Backend failed to fetch room status",
                "detail": type(e).__name__,
                "message": str(e),
            }
        ), 500


@app.get("/api/health")
def api_health():
    """Simple health check endpoint."""
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    # Bind only to localhost by default. Use a reverse proxy to expose externally.
    app.run(host="127.0.0.1", port=port)
