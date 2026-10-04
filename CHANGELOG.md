# Changelog

## v0.5.2

Rebuilds the **HeyLight Tree** preview from a frame-by-frame review of the original HeyLight application video.

### Changed

- increases the preview tree to 17 LED rows and makes it taller while keeping extra space above it so the star is no longer clipped on phones
- keeps the effect name beside the tree without shrinking the tree into a narrow column
- hides the `Color 2` and `Color 3` text labels on phone layouts while keeping their enable buttons and colour swatches accessible
- reworks `flick` as synchronized whole-tree colour changes and `flick around` as rotating diagonal light paths
- makes `random color` use individually distributed internal colours
- makes `fading` a synchronized brightness fade and `fading adv` fade through the active user palette
- makes `color change1` switch the whole tree between the chosen colours and `color change2` render the moving three-colour distributed pattern seen in the app
- makes `fall rainbow` grow a fixed rainbow from the top down, `fall snake` grow the selected colour downward, and `fall ant` move a narrow selected-colour band down the tree
- changes `moon beyond stars` to sparse twinkling points on a dark tree and `collide` to opposing moving bands
- changes `little fire` to palette-based moving horizontal colour zones instead of artificial red/orange hue shifting
- changes `random breath` to a breathing primary colour with randomly distributed secondary/tertiary accents
- rebuilds `wave up` and `wave down` as horizontal selected-colour bands that fill the tree in the corresponding direction
- rebuilds `flag` as three horizontal palette bands with the same full-pattern breathing behaviour visible in the HeyLight app
- rebuilds `heap up` with a falling bar plus progressively stacked lower rows
- rebuilds `vertical wave` as growing vertical colour paths and `snake` as a short moving segment following a serpentine LED path
- keeps user-selectable effects tied to the actual selected Home Assistant palette colours
- removes CSS arithmetic that can be unreliable in mobile Safari by precomputing animation timing values in JavaScript

## v0.5.1

Refines the bundled **HeyLight Tree** dashboard card after comparison with the original HeyLight app animation video.

### Changed

- moves the current effect name beside the tree instead of overlaying it on the tree
- removes the separate on/off status lamp/text; the power button itself is now the state indicator
- keeps the last selected effect, colours, brightness and effect speed visible while the physical light is off
- no longer falls back to displaying `normal` just because the light is off or an effect attribute is temporarily absent
- stores the last UI settings locally so the card can preserve them across dashboard reloads while the light is off
- replaces the generic animation groups with effect-specific animation patterns modelled after the original HeyLight application video
- keeps user-selected palette colours as the colours used by the animated preview where the physical effect accepts user colours
- adds separate visual behaviour for normal, flick, flick around, random color, fading, fading adv, color change1, color change2, fall rainbow, fall snake, fall ant, moon beyond stars, collide, little fire, random breath, wave down, flag, heap up, vertical wave, snake and wave up

## v0.5.0

Adds the bundled **HeyLight Tree** Home Assistant dashboard card.

### Added

- animated modern Christmas-tree visualization that follows the current HeyLight effect and active palette
- live power/availability state and current effect display
- power toggle and effect selector
- primary RGB colour picker
- automatic discovery and control of `Effect color 2` and `Effect color 3`, including enable/disable state
- brightness control
- effect speed control when the speed entity is available
- effect-aware animations for flicker/fire, fade/breathe, colour change, rainbow, snake/ant chase, stars, collide, wave and flag scenes
- Hungarian UI labels when Home Assistant uses Hungarian, with English fallback
- automatic frontend module loading from the integration; no separate Lovelace resource is required
- dashboard card picker registration and entity suggestions for compatible HeyLight lights

### Changed

- adds the Home Assistant `frontend` dependency so the bundled card can be registered safely

## v0.4.9

Keeps device-side timing reliable by avoiding automatic clock writes immediately before Scheduler transitions.

### Changed

- time synchronization now happens when timing settings are saved instead of shortly before each scheduled event
- scheduled on/off state feedback still uses lightweight readback attempts at +1 s, +4 s and +8 s when needed

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

Adds device-side timing support matching the official Heylight 2.3.18 Timing screen.

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
- Repeat OFF mirrors the Heylight app by using the current month/day
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
