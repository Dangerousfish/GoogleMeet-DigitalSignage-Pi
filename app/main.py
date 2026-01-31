"""Main application entry point for the room signage service.

This module defines the FastAPI application, configures logging, manages
in‑memory caching of room metadata and occupancy data, and serves both a
JSON API and a minimal HTML user interface. It is designed to run on
resource‑constrained devices such as the Raspberry Pi, so it avoids heavy
frameworks and unnecessary dependencies.

Endpoints:
  - ``/api/rooms``: return the list of room resources from Directory API.
  - ``/api/status``: compute and return room occupancy state.
  - ``/healthz``: simple health check endpoint.
  - ``/``: serve the wallboard UI.

The service uses a simple cache with a threading lock to avoid calling
Google APIs more often than necessary. Errors from Google APIs are
captured and surfaced via the ``lastError`` field of JSON responses.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .config import settings
from .google_client import freebusy_for_calendars, list_rooms
from .models import BusyBlock, RoomStatus

logger = logging.getLogger("room_signage")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

app = FastAPI(title="Room Signage Service")

# CORS configuration: disabled by default because the kiosk and API run on the same origin.
# If you need to expose the API to other hosts, set ENABLE_CORS=yes in the environment and
# the middleware will be applied.
if str(settings.__dict__.get("enable_cors", "")).lower() in {"1", "true", "yes"}:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "rooms": None,
    "rooms_fetched_at": None,
    "status": None,
    "status_fetched_at": None,
    "last_error": None,
}


def _utcnow() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(timezone.utc)


def _cache_fresh(ts: Optional[datetime], max_age_seconds: int) -> bool:
    """Return True if the timestamp ``ts`` is within ``max_age_seconds`` of now."""
    if ts is None:
        return False
    return (_utcnow() - ts).total_seconds() < max_age_seconds


def _get_rooms_cached() -> List[dict]:
    """Retrieve rooms, using the cache if it is fresh.

    The rooms list is refreshed on a slower cadence than occupancy status; by default
    it is considered stale after ``refresh_seconds * 10`` seconds (minimum 300s).
    """
    max_age = max(settings.refresh_seconds * 10, 300)
    with _cache_lock:
        if _cache_fresh(_cache.get("rooms_fetched_at"), max_age) and _cache.get("rooms") is not None:
            return _cache["rooms"]
    try:
        rooms = list_rooms()
        with _cache_lock:
            _cache["rooms"] = rooms
            _cache["rooms_fetched_at"] = _utcnow()
            _cache["last_error"] = None
        return rooms
    except Exception as exc:
        logger.exception("Error fetching rooms: %s", exc)
        with _cache_lock:
            _cache["last_error"] = f"ROOMS_ERROR: {exc}"
            if _cache.get("rooms") is not None:
                return _cache["rooms"]
        raise


def _compute_status() -> List[RoomStatus]:
    """Compute occupancy status for all rooms in the cache."""
    now = _utcnow()
    window_start = now - timedelta(minutes=1)
    window_end = now + timedelta(minutes=max(settings.soon_minutes, 10) + 180)

    rooms = _get_rooms_cached()
    # Build list of calendar IDs and map them back to room records.
    calendar_ids: List[str] = []
    room_map: Dict[str, dict] = {}
    for room in rooms:
        cal_id = room.get("resourceEmail")
        if not cal_id:
            continue
        calendar_ids.append(cal_id)
        room_map[cal_id] = room

    # Batch free/busy queries to avoid hitting request size limits.
    batch_size = 40
    busy_map: Dict[str, List] = {}
    for i in range(0, len(calendar_ids), batch_size):
        chunk = calendar_ids[i : i + batch_size]
        try:
            chunk_busy = freebusy_for_calendars(chunk, window_start, window_end)
            busy_map.update(chunk_busy)
        except Exception as exc:
            logger.exception("Error fetching FreeBusy for calendars: %s", exc)
            # on failure we note the error and fall back to empty busy_map for this chunk
            with _cache_lock:
                _cache["last_error"] = f"STATUS_ERROR: {exc}"
            for cid in chunk:
                busy_map[cid] = []

    soon_cutoff = now + timedelta(minutes=settings.soon_minutes)
    statuses: List[RoomStatus] = []
    for cal_id in calendar_ids:
        r = room_map.get(cal_id, {})
        blocks = busy_map.get(cal_id, [])

        # Determine occupancy state
        is_busy_now = any(bstart <= now < bend for (bstart, bend) in blocks)
        is_soon = (not is_busy_now) and any(now <= bstart <= soon_cutoff for (bstart, bend) in blocks)

        # Determine next change
        next_change: Optional[datetime] = None
        if is_busy_now:
            endings = [bend for (bstart, bend) in blocks if bstart <= now < bend]
            next_change = min(endings) if endings else None
        else:
            starts = [bstart for (bstart, bend) in blocks if bstart >= now]
            next_change = min(starts) if starts else None

        statuses.append(
            RoomStatus(
                roomId=r.get("resourceId", cal_id),
                roomName=r.get("resourceName") or cal_id,
                buildingId=r.get("buildingId"),
                floorName=r.get("floorName"),
                capacity=r.get("capacity"),
                isBusyNow=is_busy_now,
                isSoon=is_soon,
                nextChangeIso=next_change.isoformat().replace("+00:00", "Z") if next_change else None,
                busyBlocks=[
                    BusyBlock(
                        start=bstart.isoformat().replace("+00:00", "Z"),
                        end=bend.isoformat().replace("+00:00", "Z"),
                    )
                    for (bstart, bend) in blocks if bend > now - timedelta(minutes=5)
                ][:4],
            )
        )

    # Sort for stable ordering: buildingId, floorName, roomName
    statuses.sort(key=lambda s: ((s.buildingId or ""), (s.floorName or ""), s.roomName.lower()))
    return statuses


@app.get("/api/rooms")
def api_rooms() -> Dict[str, Any]:
    """Return the list of room resources from the Directory API."""
    try:
        rooms = _get_rooms_cached()
        with _cache_lock:
            last_error = _cache.get("last_error")
        return {"count": len(rooms), "items": rooms, "lastError": last_error}
    except Exception as exc:
        # propagate as HTTP 500 with details
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    """Return computed occupancy status for all rooms."""
    with _cache_lock:
        if _cache_fresh(_cache.get("status_fetched_at"), settings.refresh_seconds) and _cache.get("status") is not None:
            return _cache["status"]
    try:
        statuses = _compute_status()
        payload = {
            "generatedAt": _utcnow().isoformat().replace("+00:00", "Z"),
            "refreshSeconds": settings.refresh_seconds,
            "soonMinutes": settings.soon_minutes,
            "defaultBuildingId": settings.default_building_id,
            "items": [s.model_dump() for s in statuses],
            "lastError": None,
        }
        with _cache_lock:
            _cache["status"] = payload
            _cache["status_fetched_at"] = _utcnow()
            # Do not clear last_error here; errors captured during _compute_status are kept
        return payload
    except Exception as exc:
        logger.exception("Error computing status: %s", exc)
        with _cache_lock:
            last_error = _cache.get("last_error")
        if _cache.get("status") is not None:
            # Serve stale status with error
            stale = dict(_cache["status"])
            stale["lastError"] = last_error
            return stale
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    """Health check endpoint for monitoring."""
    return {"ok": True, "time": _utcnow().isoformat().replace("+00:00", "Z")}


@app.get("/", response_class=HTMLResponse)
def signage_page() -> HTMLResponse:
    """Serve the single page wallboard application.

    The UI is intentionally embedded here rather than in a separate template or static file.
    This makes deployment easier on devices with limited resources and avoids the need
    for a frontend build chain.
    """
    # CSS variables for easy theme customisation.
    css_vars = """
    :root {
      --bg: #0b0d12;
      --fg: #e9eefc;
      --tile-bg: rgba(255,255,255,0.04);
      --tile-border: rgba(255,255,255,0.10);
      --busy-bg: rgba(255, 60, 80, 0.12);
      --busy-border: rgba(255, 60, 80, 0.30);
      --soon-bg: rgba(255, 200, 70, 0.10);
      --soon-border: rgba(255, 200, 70, 0.30);
      --free-bg: rgba(70, 220, 140, 0.10);
      --free-border: rgba(70, 220, 140, 0.28);
      --title-size: 24px;
      --room-name-size: 20px;
      --tile-min-height: 140px;
    }
    """
    html = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Room Signage</title>
  <style>
    {{css_vars}}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial;
      background: var(--bg);
      color: var(--fg);
    }}
    header {{
      display: flex;
      gap: 16px;
      align-items: baseline;
      padding: 18px 22px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }}
    h1 {{ margin: 0; font-size: var(--title-size); font-weight: 650; letter-spacing: 0.2px; }}
    .meta {{ opacity: 0.8; font-size: 14px; }}
    .filters {{
      display: flex; gap: 10px; margin-left: auto; align-items: center;
    }}
    select {{
      background: #121728; color: var(--fg); border: 1px solid rgba(255,255,255,0.12);
      padding: 10px 12px; border-radius: 12px; font-size: 14px;
    }}
    main {{ padding: 18px 22px 28px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .tile {{
      border-radius: 16px;
      padding: 16px 16px 14px;
      border: 1px solid var(--tile-border);
      box-shadow: 0 8px 30px rgba(0,0,0,0.25);
      background: var(--tile-bg);
      min-height: var(--tile-min-height);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .topline {{
      display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;
    }}
    .name {{ font-size: var(--room-name-size); font-weight: 700; line-height: 1.15; }}
    .tag {{
      font-size: 12px; padding: 7px 10px; border-radius: 999px; white-space: nowrap;
      border: 1px solid rgba(255,255,255,0.14); opacity: 0.95;
    }}
    .sub {{
      margin-top: 8px; font-size: 13px; opacity: 0.86;
      display: flex; gap: 10px; flex-wrap: wrap;
    }}
    .bottom {{
      display: flex; justify-content: space-between; align-items: baseline; gap: 10px;
      margin-top: 14px; font-size: 13px; opacity: 0.86;
    }}
    .errorbar {{
      margin: 14px 22px 0;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(255, 165, 0, 0.10);
      font-size: 13px;
    }}
    .busy {{ background: var(--busy-bg); border-color: var(--busy-border); }}
    .free {{ background: var(--free-bg); border-color: var(--free-border); }}
    .soon {{ background: var(--soon-bg); border-color: var(--soon-border); }}
    .muted {{ opacity: 0.75; }}
  </style>
</head>
<body>
  <header>
    <h1>Meeting rooms</h1>
    <div class="meta" id="meta">Loading…</div>
    <div class="filters">
      <select id="building"></select>
      <select id="floor"></select>
    </div>
  </header>
  <div id="error" class="errorbar" style="display:none;"></div>
  <main>
    <div class="grid" id="grid"></div>
  </main>
<script>
const REFRESH_MS = {settings.refresh_seconds} * 1000;
const DEFAULT_BUILDING = {json.dumps(settings.default_building_id or "")} ;

function uniq(arr) {{
  return [...new Set(arr.filter(x => x !== null && x !== undefined && String(x).trim() !== ""))];
}}
function isoToLocal(iso) {{
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString([], {{hour: '2-digit', minute: '2-digit'}});
}}
function setSelectOptions(sel, values, placeholder) {{
  sel.innerHTML = "";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = placeholder;
  sel.appendChild(opt0);
  values.forEach(v => {{
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    sel.appendChild(o);
  }});
}}
function tileClass(item) {{
  if (item.isBusyNow) return "tile busy";
  if (item.isSoon) return "tile soon";
  return "tile free";
}}
function statusTag(item) {{
  if (item.isBusyNow) return "Occupied";
  if (item.isSoon) return "Booked soon";
  return "Vacant";
}}
function nextLine(item) {{
  if (!item.nextChangeIso) return "No upcoming bookings";
  const t = isoToLocal(item.nextChangeIso);
  if (item.isBusyNow) return `Free at ${t}`;
  return `Booked at ${t}`;
}}
function render(items) {{
  const grid = document.getElementById("grid");
  const bSel = document.getElementById("building");
  const fSel = document.getElementById("floor");
  const b = bSel.value;
  const f = fSel.value;
  let filtered = items;
  if (b) filtered = filtered.filter(x => (x.buildingId || "") === b);
  if (f) filtered = filtered.filter(x => (x.floorName || "") === f);
  grid.innerHTML = "";
  filtered.forEach(item => {{
    const div = document.createElement("div");
    div.className = tileClass(item);
    const top = document.createElement("div");
    top.className = "topline";
    const left = document.createElement("div");
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = item.roomName;
    left.appendChild(name);
    const sub = document.createElement("div");
    sub.className = "sub";
    const parts = [];
    if (item.buildingId) parts.push(`Building: ${item.buildingId}`);
    if (item.floorName) parts.push(`Floor: ${item.floorName}`);
    if (item.capacity) parts.push(`Capacity: ${item.capacity}`);
    sub.textContent = parts.join(" · ");
    left.appendChild(sub);
    const tag = document.createElement("div");
    tag.className = "tag";
    tag.textContent = statusTag(item);
    top.appendChild(left);
    top.appendChild(tag);
    const bottom = document.createElement("div");
    bottom.className = "bottom";
    const next = document.createElement("div");
    next.textContent = nextLine(item);
    const hint = document.createElement("div");
    hint.className = "muted";
    hint.textContent = item.isBusyNow ? "In a meeting" : (item.isSoon ? "Get ready" : "Available now");
    bottom.appendChild(next);
    bottom.appendChild(hint);
    div.appendChild(top);
    div.appendChild(bottom);
    grid.appendChild(div);
  }});
}}
async function refresh() {{
  try {{
    const r = await fetch("/api/status", {{cache: "no-store"}});
    const data = await r.json();
    const meta = document.getElementById("meta");
    const err = document.getElementById("error");
    meta.textContent = `Updated ${new Date(data.generatedAt).toLocaleTimeString([], {{hour:'2-digit', minute:'2-digit'}})} · refresh ${data.refreshSeconds}s · soon ${data.soonMinutes}m`;
    if (data.lastError) {{
      err.style.display = "block";
      err.textContent = `Warning: ${data.lastError}`;
    }} else {{
      err.style.display = "none";
      err.textContent = "";
    }}
    const items = data.items || [];
    const buildings = uniq(items.map(x => x.buildingId));
    const floors = uniq(items.map(x => x.floorName));
    const bSel = document.getElementById("building");
    const fSel = document.getElementById("floor");
    const prevB = bSel.value;
    const prevF = fSel.value;
    setSelectOptions(bSel, buildings, "All buildings");
    setSelectOptions(fSel, floors, "All floors");
    if (buildings.includes(prevB)) bSel.value = prevB;
    if (floors.includes(prevF)) fSel.value = prevF;
    if (!bSel.value && DEFAULT_BUILDING && buildings.includes(DEFAULT_BUILDING)) {{
      bSel.value = DEFAULT_BUILDING;
    }}
    render(items);
  }} catch (e) {{
    const err = document.getElementById("error");
    err.style.display = "block";
    err.textContent = `Warning: failed to refresh: ${e}`;
  }}
}}
document.getElementById("building").addEventListener("change", refresh);
document.getElementById("floor").addEventListener("change", refresh);
refresh();
setInterval(refresh, REFRESH_MS);
</script>
</body>
</html>
"""  # noqa: E501
    return HTMLResponse(content=html.replace("{css_vars}", css_vars))