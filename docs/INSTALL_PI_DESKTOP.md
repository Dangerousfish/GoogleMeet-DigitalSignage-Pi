# Install on Raspberry Pi OS Desktop

This guide explains how to install and configure the room signage solution on
a Raspberry Pi 4 Model B (8 GB) running Raspberry Pi OS Desktop (Bookworm or later).
The Desktop variant provides a full graphical environment (LXDE) so you don’t
need to set up X11 manually. The same steps will also work on a Pi 3, but the
extra RAM of the Pi 4 is recommended for smoother browser performance.

## Prerequisites
- Raspberry Pi 4 Model B (8 GB)
- Raspberry Pi OS Desktop (latest stable release) installed
- Basic familiarity with the terminal

## Steps

1. **Update system**

   ```bash
   sudo apt update
   sudo apt full-upgrade -y
   sudo reboot
   ```

2. **Create users and directories**

   Create a system account for the API service (`roomsign`) and optionally
   a separate account for the kiosk (`kiosk`). Running the kiosk as its own user
   keeps file permissions tidy.

   ```bash
   sudo adduser --disabled-password --gecos "" roomsign
   sudo adduser --disabled-password --gecos "" kiosk
   sudo usermod -aG video,audio,render,input,netdev roomsign
   sudo usermod -aG video,audio,render,input,netdev kiosk

   sudo mkdir -p /opt/room-signage/{app,config,logs}
   sudo chown -R roomsign:roomsign /opt/room-signage
   ```

3. **Install packages**

   On the Desktop image most graphical components are already installed.
   You only need Python and Chromium:

   ```bash
   sudo apt install -y \
     python3 python3-venv python3-pip \
     chromium-browser unclutter \
     fonts-dejavu-core
   ```

4. **Backend setup**

   Create a Python virtual environment and install the dependencies.
   Run these commands as the `roomsign` user:

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

   Install the provided systemd unit file into `/etc/systemd/system/room-signage.service` and enable it:

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

   Reload systemd and start the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now room-signage.service
   ```

7. **Kiosk setup**

   Configure the Pi to autologin as the `kiosk` user into the desktop session and
   launch Chromium in kiosk mode at boot:

   - Enable auto‑login for the `kiosk` user via `sudo raspi-config` → System Options → Boot / Auto Login → Desktop Autologin.
   - Copy `kiosk/kiosk.sh` from this repository to `/home/kiosk/kiosk.sh` and make it executable (`chmod +x`).
   - Create an autostart file so LXDE runs the kiosk script on login. For the
     `kiosk` user, create a file at `/home/kiosk/.config/lxsession/LXDE-pi/autostart` containing:

     ```
     @lxpanel --profile LXDE-pi
     @pcmanfm --desktop --profile LXDE-pi
     @bash -c "/home/kiosk/kiosk.sh"
     ```

     The first two lines are standard for LXDE; the last line launches the
     kiosk script. The script will hide the mouse cursor (`unclutter`) and
     start Chromium in kiosk mode pointing at the local wallboard.

   - Ensure the file is owned by `kiosk` and has correct permissions.

8. **Reboot and test**

   Reboot the Pi. On boot, the API should start on `127.0.0.1:8080` and the
   kiosk user should log in automatically and display the wallboard page.

## Updating

To update the code, pull the latest repository contents and replace the
`/opt/room-signage/app` directory. Then restart the systemd service:

```
sudo systemctl restart room-signage.service
```

## Troubleshooting

If the screen is blank, check that the backend is running:

```
curl -s http://127.0.0.1:8080/healthz
```

If that fails, view the service logs:

```
sudo journalctl -u room-signage.service -n 50 --no-pager
```

---

This document covers the Raspberry Pi OS Desktop setup. For Raspberry Pi OS
Lite instructions, see `docs/INSTALL_PI_LITE.md`.