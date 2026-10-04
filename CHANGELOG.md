# Changelog

## v0.4.8

Improves device-side timer accuracy and state feedback without bringing back continuous polling.

### Changed

- measures the light string's Bluetooth Mesh clock offset against Home Assistant
- records the measured clock drift in diagnostics
- synchronizes the light string clock 90 seconds before the next configured on/off Scheduler transition
- keeps the existing synchronization when timing settings are written
- checks the physical power state at +1 s after a timer transition, then retries at +4 s and +8 s only when needed
- exposes `clock_offset_seconds`, `last_pre_sync_offset_seconds`, and `last_clock_sync_unix` in diagnostics

## v0.4.7

Refreshes the HeyLight brand assets used by the custom integration.

## v0.4.6

Fixes a regression introduced by aggressive power-state polling.

### Changed

- removed the continuous 5-second vendor power polling
- Home Assistant now reads the physical power state only after reconnect and shortly after the configured device-side on/off timer transitions
- this keeps scheduler-driven state changes visible in Home Assistant without continuously querying the Telink controller
- retained the local Home Assistant brand assets; the integration detail page itself does not currently render a large custom logo even when `logo.png` is available

## v0.4.5

Improves state synchronization for device-side timing and refreshes integration branding.

### Changed

- the main light power state is now queried from the physical device every 5 seconds while the Mesh Proxy connection is available
- scheduler-triggered, official-app, or other external power changes now update the Home Assistant light entity automatically
- replaced the integration logo with a rectangular brand asset
- added Retina and dark-mode logo variants so Home Assistant can use the correct asset on high-density dark-mode displays

## v0.4.0

Adds device-side timing support matching the official HeyLight 2.3.18 Timing screen.

### Added

- `Timing` Configuration switch
- `Timing repeat` Configuration switch
- `Turn on time` Configuration time entity
- `Turn off time` Configuration time entity
- direct Bluetooth Mesh Scheduler Action Get/Set support
- scheduler capability details in diagnostics
- protocol documentation for Scheduler Server `0x1206` / Scheduler Setup Server `0x1207`

### Timing behaviour

- Scheduler slot 1 controls Turn On
- Scheduler slot 2 controls Turn Off
- Timing OFF writes `No Action` to both slots
- Repeat ON uses all seven weekdays
- Repeat OFF mirrors the HeyLight app by using the current month/day
- settings are stored in the light string itself, not as Home Assistant automations

## v0.3.0

First beta release with the currently verified feature set for HeyLight PID `0xFAC8`, firmware `51`.

### Added

- Share Device setup from QR image or decoded QR JSON text
- local Bluetooth SIG Mesh control through Home Assistant Bluetooth
- power on/off
- RGB colour control
- working brightness control by scaling E6 scene colours
- effect speed control from 1 to 10
- effect-specific support for 0, 1, 2, or up to 3 user colours
- automatic Bluetooth reconnect
- Mesh Network ID and cryptographically validated Node Identity discovery
- diagnostics with reconnect/connection information while omitting mesh secrets
- HACS-compatible GitHub releases
- dedicated HeyLight integration branding/icon
- protocol documentation in `docs/PROTOCOL.md`

### Verified effects

- normal
- flick
- flick around
- random color
- fading
- fading adv
- color change1
- color change2
- fall rainbow
- fall snake
- fall ant
- moon beyond stars
- collide
- little fire
- random breath
- wave down
- flag
- heap up
- vertical wave
- snake
- wave up

### Product-specific fixes included

- `fall rainbow` maps to working scene 45 (`themeRainbowFixedcolor`) instead of inactive generic scene 10
- `random color` and `fall rainbow` do not expose user colour controls
- `moon beyond stars`, `random breath`, and `snake` expose exactly two colour slots
- brightness uses RGB scene scaling because vendor F3 brightness produces no visible response on the tested firmware
- BLE reconnect and Mesh Node Identity handling hardened for long-running Home Assistant use
