#!/usr/bin/env bash
#
# Launch Chromium in kiosk mode pointing at the local wallboard service.
#
# This script disables screen blanking, hides the mouse cursor, and starts
# Chromium with flags suitable for a single‑purpose kiosk. It assumes that
# the backend is available at http://127.0.0.1:8080/.

set -euo pipefail

# URL to load. Override by passing a first argument.
URL="${1:-http://127.0.0.1:8080/}"

# Prevent the display from blanking.
xset s off
xset s noblank
xset -dpms

# Hide the cursor after a short delay.
unclutter -idle 0.25 -root &

# Launch Chromium. Use --autoplay-policy to avoid sound issues if you add
# audio later. The long update interval prevents automatic updates which
# could break kiosk sessions.
exec chromium-browser \
  --kiosk \
  --incognito \
  --noerrdialogs \
  --disable-infobars \
  --disable-features=TranslateUI \
  --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  "$URL"