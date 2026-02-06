#!/usr/bin/env bash
# Kiosk autostart script for Raspberry Pi running a Cage + Chromium kiosk.
# This script is intended to be executed as the kiosk user from
# ~/.bash_profile or a systemd unit.  It launches a D‑Bus session,
# then runs cage to host Chromium in Wayland kiosk mode.

set -euo pipefail

# Only start when invoked on the physical console tty1.  This avoids
# accidental invocation from SSH sessions.
if [ "$(tty)" != "/dev/tty1" ]; then
  exit 0
fi

# Set up the runtime directory for user services if not already present.
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Enable Wayland for Chromium (ozone platform) and DBus for Cage
export MOZ_ENABLE_WAYLAND=1

# Change to home directory to avoid permission issues reading current
# working directory (e.g. when launched via sudo).  The start script
# should be owned by the kiosk user.
cd "$HOME"

# Launch cage running Chromium pointing at the rooms page.  Use dbus-run-session
# to ensure a D‑Bus session bus is available, which Chromium expects.
exec dbus-run-session -- cage -- chromium \
  --kiosk \
  --no-first-run \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --incognito \
  --overscroll-history-navigation=0 \
  --ozone-platform=wayland \
  --enable-features=UseOzonePlatform \
  http://localhost/rooms/
