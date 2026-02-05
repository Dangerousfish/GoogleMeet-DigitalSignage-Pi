# Raspberry Pi Google Workspace Room Signage

Lightweight digital signage for offices that displays real-time meeting room occupancy (Vacant / Occupied / Booked Soon) using Google Workspace room resource calendars.

Designed to run entirely on a single Raspberry Pi 4 Model B (8 GB) using:

• Google Workspace APIs  
• FastAPI backend  
• Chromium kiosk mode  
• Raspberry Pi OS Desktop (latest stable release)

No Docker. No heavy frameworks. No paid signage software.

---

## ✨ Features

- Real‑time room occupancy from Google Calendar Free/Busy
- Automatic room inventory from Google Directory
- Privacy‑preserving (no meeting titles or attendees)
- Colour‑coded tiles:
  - Green → Vacant
  - Amber → Booked Soon
  - Red → Occupied
- Building & floor metadata support
- Auto‑refreshing wallboard UI
- Fully offline‑capable front‑end after load
- Runs backend and kiosk on the same Pi

---

## 🧱 Architecture

```
Google Workspace
   │
   │  (Admin SDK + Calendar FreeBusy)
   ▼
FastAPI Backend (localhost:8080)
   │
   ▼
Single‑Page HTML Wallboard
   │
   ▼
Chromium Kiosk (Raspberry Pi)
```

---

## 🖥 Hardware

Minimum tested target:

- Raspberry Pi 4 Model B (8 GB)
- 16 GB or larger microSD
- Ethernet or Wi‑Fi
- HDMI display

---

## 🔐 Security Model

- Service Account with Domain‑Wide Delegation
- Read‑only scopes:
  - `admin.directory.resource.calendar.readonly`
  - `calendar.freebusy`
- No user OAuth flows
- No meeting content fetched

---

## 🧪 Data Sources

- Google Admin SDK Directory API (room resources)
- Google Calendar FreeBusy API

Room occupancy is inferred purely from room calendar busy blocks.

---

## 🚀 Installation Overview

High‑level flow:

1. Flash Raspberry Pi OS Desktop (latest stable release)
2. Install Python + Chromium
3. Create service account & enable APIs
4. Copy backend files
5. Configure environment variables
6. Register backend as systemd service
7. Configure kiosk autologin + Chromium
8. Reboot

Full step‑by‑step instructions are in:

👉 `docs/INSTALL_PI_DESKTOP.md`

---

## 📁 Repository Structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── google_client.py
│   ├── main.py
│   ├── models.py
│   └── requirements.txt
│
├── kiosk/
│   ├── kiosk.sh
│   ├── xinitrc
│   ├── bash_profile
│   └── autologin.conf
│
├── systemd/
│   └── room-signage.service
│
├── docs/
│   ├── INSTALL_PI_DESKTOP.md
│   ├── INSTALL_PI_LITE.md
│   ├── SECURITY.md
│   └── ARCHITECTURE.md
│
├── LICENSE
├── README.md
└── .gitignore
```

---

## ⚙ Configuration (Environment Variables)

File:

```
/opt/room-signage/config/room-signage.env
```

Example:

```
GOOGLE_SERVICE_ACCOUNT_JSON=/opt/room-signage/config/service-account.json
GOOGLE_IMPERSONATE_USER=room-signage-admin@company.com
GOOGLE_CUSTOMER=my_customer

REFRESH_SECONDS=60
SOON_MINUTES=10
DEFAULT_BUILDING_ID=3
```

---

## 🌍 Endpoints

```
GET /            Wallboard UI
GET /api/status  Computed room status
GET /api/rooms   Raw directory room list
GET /healthz     Health check
```

---

## 🔄 Status States

| State       | Meaning                              |
| ----------- | ------------------------------------ |
| Vacant      | No meeting currently in progress     |
| Occupied    | Busy block covering current time     |
| Booked Soon | Meeting starting within SOON_MINUTES |

---

## 🎨 Styling

The wallboard UI is intentionally implemented as a single HTML page served by the backend (`GET /`). This keeps the Raspberry Pi footprint (including Pi 4) small and avoids a build pipeline.

### Quick customisation

All styling lives in the `<style>` block in `app/main.py` inside `signage_page()`.

Recommended edits:

- **Tile size** (readability at distance):
  - `.tile { min-height: 140px; }`
  - `.name { font-size: 20px; }`

- **Grid density** (more rooms vs bigger tiles):
  - `.grid { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }`
  - Increase `minmax(...)` for larger tiles, reduce for more columns.

- **Colour theme**
  - Background: `body { background: #293d32; }`
  - Text: `body { color: #ffffff; }`
  - Tile base: `.tile { background: rgba(255,255,255,0.05); }`
  - The “busy” and “soon” states are tinted using the highlight colour (#ff8fa2); free states use neutral tones.

If you prefer a different palette, adjust the CSS variables defined in `app/main.py` (see `--bg`, `--fg` and the various state colours).

### Accessibility and legibility

For a shared screen viewed across a room:

- Keep contrast high (dark background + light text is intentional)
- Avoid thin fonts and small type
- Use short labels (“Vacant”, “Occupied”, “Booked soon”)
- Ensure colour is not the only indicator (status text is always shown)

### Raspberry Pi performance rules (do not break these)

- Avoid heavy web fonts and large images
- Avoid CSS filters and expensive effects
- Avoid animations or keep them minimal
- Keep refresh interval ≥ 45 seconds (`REFRESH_SECONDS`)
- Keep the UI dependency‑free (no React/Vue build toolchain)

### Optional: Hide filters for a shared office screen

If the wallboard is always used for a single office building, set:

```
DEFAULT_BUILDING_ID=<GoogleBuildingID>
```

The UI will auto‑filter to that building. You can also remove the `<select>` elements from the HTML if you want a fixed view with no controls.

---

## 🛠 Operations

Restart backend:

```
sudo systemctl restart room-signage.service
```

View logs:

```
sudo journalctl -u room-signage.service -f
```

---

## 📈 Scaling

- Hundreds of rooms supported
- FreeBusy queries batched
- In‑memory caching
- Single Pi can comfortably drive one wallboard

For multiple screens, simply point more Pis at the same backend.

---

## ⚠ Limitations

- Booking‑based occupancy only
- Does not detect physical presence
- No touch interaction (by design)

---

## 🧭 Roadmap Ideas

- Per‑room door displays
- QR code booking links
- “Available rooms right now” priority row
- Dark/light themes
- Local time‑zone override
- Health check endpoint

---

## 📜 Licence

PolyForm Noncommercial Licence 1.0.0  
Free for non‑commercial use. Commercial use prohibited.

---

## 🤝 Contributions

PRs welcome. Keep it lightweight, dependency‑minimal, and Pi‑friendly.