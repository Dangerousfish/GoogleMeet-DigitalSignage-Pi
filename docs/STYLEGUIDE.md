# Style Guide

This document explains how to customise the appearance of the room signage wallboard
and outlines performance considerations for low‑resource devices such as the
Raspberry Pi 3. The UI is intentionally simple to keep the codebase small and
the rendering fast.

## Theme Customisation

The CSS for the wallboard lives in the `<style>` block embedded within
`app/main.py`. All configurable values are defined as CSS custom properties
(variables) under the `:root` selector. To change the look and feel, edit
these variables:

| Variable             | Description                                           | Example value                |
|----------------------|-------------------------------------------------------|------------------------------|
| `--bg`               | Page background colour                                | `#0b0d12`                    |
| `--fg`               | Default foreground/text colour                        | `#e9eefc`                    |
| `--tile-bg`          | Tile background colour                                | `rgba(255,255,255,0.04)`     |
| `--tile-border`      | Tile border colour                                    | `rgba(255,255,255,0.10)`     |
| `--busy-bg`          | Background colour for occupied rooms                  | `rgba(255,60,80,0.12)`       |
| `--busy-border`      | Border colour for occupied rooms                      | `rgba(255,60,80,0.30)`       |
| `--soon-bg`          | Background colour for rooms booked soon               | `rgba(255,200,70,0.10)`      |
| `--soon-border`      | Border colour for rooms booked soon                   | `rgba(255,200,70,0.30)`      |
| `--free-bg`          | Background colour for vacant rooms                    | `rgba(70,220,140,0.10)`      |
| `--free-border`      | Border colour for vacant rooms                        | `rgba(70,220,140,0.28)`      |
| `--title-size`       | Font size for the page title                          | `24px`                       |
| `--room-name-size`   | Font size for individual room names                   | `20px`                       |
| `--tile-min-height`  | Minimum height of each room tile                      | `140px`                      |

To change a colour or size, update the corresponding variable. For example,
to use a lighter background and a dark theme you might set:

```css
--bg: #f5f5f5;
--fg: #222222;
--tile-bg: rgba(0,0,0,0.04);
```

These variables cascade through the rest of the styles, so you need only edit
them once.

## Readability and Legibility

Room signage is often viewed from a distance. Keep these principles in mind:

* **Contrast:** Ensure high contrast between text and background. Dark
  backgrounds with light text (or vice versa) help readability.
* **Font sizes:** Avoid making fonts too small. The provided defaults are
  suitable for displays up to 1080p viewed at several metres.
* **Labels:** Use concise labels (“Vacant”, “Occupied”, “Booked soon”) so
  there is no ambiguity.
* **Spacing:** Adequate padding and margins make the grid easier to scan.

## Performance Guidelines

The Raspberry Pi 3 has limited RAM (1 GiB) and CPU. To keep the UI responsive:

* **Avoid heavy fonts or external web fonts.** Use system fonts to reduce
  memory usage.
* **No CSS animations or transitions.** Even simple animations can consume
  CPU cycles. If you add animations later, test on the Pi.
* **Limit image usage.** The UI deliberately contains no images. If you
  choose to add icons or logos, compress them and avoid large files.
* **Refresh interval:** A longer refresh interval reduces CPU usage. The
  default (`REFRESH_SECONDS=60`) is sufficient for most offices.
* **Kiosk flags:** Chromium is launched with a `--check-for-update-interval` set
  to a very large value to prevent update checks from using network and CPU.

## Removing Filters

If you operate a single screen for a single building, you can remove the
building and floor dropdown filters entirely. Edit `app/main.py` and remove
the `<select>` elements and their associated logic in the JavaScript. You
should also hardcode the default building ID in your environment file via
`DEFAULT_BUILDING_ID` to make the API return your desired filter value by
default.

## Theming via External CSS

For more advanced branding, consider extracting the `<style>` block into an
external CSS file served by a static endpoint. This keeps your HTML cleaner
and allows for easier updates without editing Python code. However, this
requires adjusting `signage_page()` to reference the static file.