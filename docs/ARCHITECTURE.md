# Architecture Overview

This document provides a high‑level overview of the components and
communication flow within the Raspberry Pi Google Workspace Room Signage
system.

## Components

### FastAPI backend

* Serves HTTP on `localhost:8080`.
* Uses a Google service account with domain‑wide delegation to query:
  - **Directory API** to enumerate room resources (building, floor, capacity).
  - **Calendar FreeBusy** to determine whether each room is currently busy and
    when it will next change state.
* Caches responses in memory to respect Google API quotas and to remain
  responsive if Google is temporarily unavailable.
* Exposes REST endpoints:
  - `GET /api/rooms` — raw room resource list.
  - `GET /api/status` — computed busy/free status for all rooms.
  - `GET /healthz` — simple liveness probe.
  - `GET /` — static wallboard page that fetches status via the API.

### Wallboard UI

* A single HTML page served by the backend (`/`).
* Written without frameworks (plain JS + CSS) for maximum Pi 3 performance.
* Polls the `/api/status` endpoint every `REFRESH_SECONDS` seconds and
  updates the grid of room tiles.
* Provides dropdowns to filter by building and floor; defaults to a
  pre‑configured building if set in the environment.

### Raspberry Pi kiosk

* Runs Raspberry Pi OS Lite with a minimal X11 environment.
* Launches Chromium in kiosk mode via `~kiosk/kiosk.sh`.
* Autologins the `kiosk` user on tty1, starts X and hides the mouse cursor.
* Points Chromium at `http://127.0.0.1:8080/` (the wallboard).

### Systemd service

* A unit (`systemd/room-signage.service`) runs the API under the `roomsign` user.
* References an environment file containing secrets and configuration.
* Restarts automatically on failure.

## Data flow

```
┌─────────────────────────┐      ┌───────────────────────┐      ┌────────────┐
│ Google Workspace        │←─────│ Service account w/DWD │────→│ FastAPI API │
│ (Directory & Calendar)  │      └───────────────────────┘      │   on Pi    │
└─────────────────────────┘                                     └─────┬──────┘
                                                                      │
                                                                      ▼
                                                         ┌───────────────────────┐
                                                         │ Wallboard UI (HTML)  │
                                                         │ served by backend     │
                                                         └────────────┬─────────┘
                                                                      │
                                                                      ▼
                                                         ┌───────────────────────┐
                                                         │ Chromium in kiosk     │
                                                         │ mode (Pi display)     │
                                                         └───────────────────────┘
```

## Why FreeBusy?

Using the Calendar FreeBusy API means the system never reads event titles,
descriptions or attendees. It only needs to know whether a room resource
calendar is busy. This preserves privacy and avoids the risk of exposing
confidential meeting information.

## Scalability

The application batches FreeBusy queries to reduce the number of HTTP
requests. With modest caching and a refresh interval of 45–60 seconds, a
single Pi can handle hundreds of rooms without issue. For multiple
displays, either run additional Pis pointing to the same backend, or
deploy the backend on a server and point all displays at that server.