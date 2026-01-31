# Install on Raspberry Pi OS Lite

This document describes how to install and configure the room signage
solution on a single Raspberry Pi 3 running Raspberry Pi OS Lite. The Pi
hosts both the backend service and the kiosk browser.

## Prerequisites

- Raspberry Pi 3 Model B or B+
- Raspberry Pi OS Lite installed (tested on Bookworm)
- Basic familiarity with the terminal

## Steps

1. **Update system**

   ```bash
   sudo apt update
   sudo apt full-upgrade -y
   sudo reboot
   ```

2. **Create users and directories**

   Create two system users: one for the API service (`roomsign`) and one for
   the kiosk (`kiosk`).

   ```bash
   sudo adduser --disabled-password --gecos "" roomsign
   sudo adduser --disabled-password --gecos "" kiosk
   sudo usermod -aG video,audio,render,input,netdev roomsign
   sudo usermod -aG video,audio,render,input,netdev kiosk
   
   sudo mkdir -p /opt/room-signage/{app,config,logs}
   sudo chown -R roomsign:roomsign /opt/room-signage
   ```

3. **Install packages**

   The Pi needs Python, Chromium, X11 and a lightweight window manager:

   ```bash
   sudo apt install -y \
     python3 python3-venv python3-pip \
     libatlas-base-dev ca-certificates \
     xserver-xorg x11-xserver-utils xinit openbox \
     chromium-browser unclutter \
     fonts-dejavu-core
   ```

4. **Backend setup**

   Create a Python virtual environment and install the dependencies.

   ```bash
   sudo -u roomsign python3 -m venv /opt/room-signage/venv
   sudo -u roomsign /opt/room-signage/venv/bin/pip install --upgrade pip
   sudo -u roomsign /opt/room-signage/venv/bin/pip install -r /opt/room-signage/app/requirements.txt
   ```

   Copy the code from this repository into `/opt/room-signage/app` on the Pi.

5. **Service account key and env**

   - Place your Google service‑account JSON into `/opt/room-signage/config/service-account.json`.
   - Create `/opt/room-signage/config/room-signage.env` based on the example in the README.
   - Ensure permissions are tight (`chmod 600`).

6. **Systemd service**

   Install the provided systemd unit file into `/etc/systemd/system/room-signage.service`:

   ```ini
   [Unit]
   Description=Room Signage (Google Workspace)
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=roomsign
   Group=roomsign
   WorkingDirectory=/opt/room-signage/app
   EnvironmentFile=/opt/room-signage/config/room-signage.env
   ExecStart=/opt/room-signage/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

   Enable and start the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now room-signage.service
   ```

7. **Kiosk setup**

   Configure the Pi to autologin as the `kiosk` user on the console, start X and launch Chromium.

   - Create `/home/kiosk/kiosk.sh` script as described in the README.
   - Create `.xinitrc` and `.bash_profile` for the `kiosk` user.
   - Use an agetty override to autologin on tty1.

8. **Reboot and test**

   After everything is in place, reboot the Pi. On boot, the API should start on
   `127.0.0.1:8080` and the kiosk should display the wallboard page.

## Updating

To update the code, pull the latest repository contents and replace the
`/opt/room-signage/app` directory. Then restart the systemd service:

```bash
sudo systemctl restart room-signage.service
```

## Troubleshooting

If the screen is blank, check that the backend is running:

```bash
curl -s http://127.0.0.1:8080/healthz
```

If that fails, view the service logs:

```bash
sudo journalctl -u room-signage.service -n 50 --no-pager
```