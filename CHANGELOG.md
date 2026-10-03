# Changelog

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
