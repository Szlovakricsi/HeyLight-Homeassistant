# HeyLight Home Assistant

Standalone Home Assistant integration for selected **HeyLight / Telink Bluetooth SIG Mesh** RGB light strings.

> Community interoperability project. Not affiliated with HeyLight, Telink, DekorTrend, Lumineo, or Home Assistant.

## Status

**v0.3.0** is the first beta release based on a fully tested HeyLight PID `0xFAC8`, firmware `51` string. Power, RGB colour, brightness, effect speed, effect selection, multi-colour palettes, QR import, and automatic Bluetooth reconnect have all been verified on the tested device.

## Features

- Fully local Bluetooth Mesh control through Home Assistant's Bluetooth stack
- No HeyLight cloud required after importing the mesh
- First-run setup from the HeyLight **Share Device QR code**
  - upload a QR screenshot/photo, or
  - paste the decoded QR JSON text
- Power on/off
- RGB colour control
- Brightness control
- Effect selector
- Effect speed control from 1 to 10
- Automatic second/third palette entities only where the active effect supports them
- Automatic Bluetooth reconnect
- Mesh Proxy Network ID and cryptographically validated Node Identity discovery
- Diagnostics without exposing mesh keys
- HACS-compatible releases

## Supported and tested device

The current implementation is verified on a HeyLight light string with:

- Bluetooth SIG Mesh / Telink
- Company ID `0x0211`
- Vendor model `0x0211:0x0000`
- Product ID `0xFAC8`
- firmware label `51`
- HeyLight `sl2c0030` family

Other HeyLight/Telink devices using the same vendor model may work, but are not yet verified.

## Effect support

The following effect behaviour has been physically verified on the tested PID `0xFAC8` / firmware `51` string.

| Effect | Scene | User colours |
|---|---:|---:|
| normal | 0 | 1 |
| flick | 1 | 1 |
| flick around | 3 | 1 |
| random color | 5 | fixed/internal |
| fading | 6 | 1 |
| fading adv | 7 | up to 3 |
| color change1 | 8 | up to 3 |
| color change2 | 9 | up to 3 |
| fall rainbow | 45 | fixed/internal |
| fall snake | 11 | up to 3 |
| fall ant | 12 | up to 3 |
| moon beyond stars | 13 | 2 |
| collide | 18 | 1 |
| little fire | 19 | up to 3 |
| random breath | 21 | 2 |
| wave down | 22 | up to 3 |
| flag | 23 | up to 3 |
| heap up | 24 | 1 |
| vertical wave | 25 | up to 3 |
| snake | 26 | 2 |
| wave up | 27 | up to 3 |

`random color` and `fall rainbow` generate their colours internally, so Home Assistant does not expose a user-selectable palette for those effects.

The tested product does **not** use generic scene 10 for the visible rainbow effect. Its working fixed-rainbow mode is HeyLight/Telink scene **45** (`themeRainbowFixedcolor`).

## Brightness

This device exposes a Telink vendor brightness command, but firmware `51` does not visibly react to that command. The integration therefore applies brightness by scaling the RGB values transmitted in each E6 scene payload.

This keeps the selected colour intact in Home Assistant: setting brightness back to 100% restores the original RGB value instead of permanently modifying it.

For `random color` and `fall rainbow`, brightness is applied to their internal/fixed palette values.

## Install with HACS

1. Open **HACS → Integrations**.
2. Open `⋮` → **Custom repositories**.
3. Add:
   `https://github.com/Szlovakricsi/HeyLight-Homeassistant`
4. Select category **Integration**.
5. Install **HeyLight**.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration → HeyLight**.

Updates are published as GitHub Releases. HACS checks repositories periodically, so a new release may not appear immediately after it is published. If needed, refresh HACS repository information or restart Home Assistant.

## Configure from the Share Device QR code

In the HeyLight app, open **Share Device** and display the QR code.

During setup, either:

- upload a screenshot/photo containing the QR code, or
- paste the decoded QR JSON text.

The JSON has this general form (all secrets below are placeholders):

```json
{
  "agent": "sl2c0030",
  "meshName": "DEMO_MESH_123456",
  "meshPwd": "XXXXXXXXXXXXXXXX",
  "nodes": [
    {
      "n": "Light String 1",
      "m": "AA:BB:CC:DD:EE:FF",
      "a": 1,
      "k": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
      "i": "...",
      "t": 64200,
      "p": {"l": 200, "f": 360, "o": 1}
    }
  ]
}
```

**Never publish your real QR JSON.** It contains Bluetooth Mesh network/application/device key material.

## Home Assistant entities

For each supported string the integration creates:

- one main Light entity for power, RGB, brightness and effect selection
- `Effect speed`, range 1–10
- `Effect color 2` and `Effect color 3` helper Light entities where the active scene supports additional palette slots

Palette helper entities become unavailable when the current effect does not support that colour slot. This is intentional.

## Bluetooth and reconnect behaviour

The tested controller advertises Bluetooth Mesh Proxy service UUID `0x1828` after provisioning.

The integration can identify the proxy using:

- a matching Mesh Network ID advertisement, or
- a cryptographically validated Mesh Node Identity derived from the imported NetKey and node unicast address.

A held GATT Mesh Proxy connection is reused for commands. If the connection drops, the integration automatically retries and reconnects when the proxy becomes available again.

Some controllers allow only one active GATT Mesh Proxy connection. While Home Assistant is connected, the HeyLight mobile app may temporarily be unable to connect to the same controller.

## Vendor protocol notes

Although the tested device exposes standard SIG lighting models, its physical LEDs are controlled through Telink vendor model `0x0211:0x0000`.

Verified vendor opcodes include:

- power Set: `E0 11 02`
- power Get: `E1 11 02`
- power Status: `E3 11 02`
- scene/effect Set: `E6 11 02`

Effect payload layout, gamma/white-balance processing and speed conversion were derived from HeyLight 2.3.18 and verified against the physical device.

More protocol details are documented in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Diagnostics

Home Assistant diagnostics include connection state, reconnect counters, node/product metadata and recent connection errors. Mesh secrets are intentionally excluded.

If the device becomes unavailable unexpectedly, download integration diagnostics from **Settings → Devices & services → HeyLight → Download diagnostics** before reloading the integration, if possible.

## Privacy and security

The imported Share Device JSON is stored locally in the Home Assistant config entry. It is not uploaded to this project's GitHub repository or sent to a HeyLight cloud service by this integration.

Diagnostics omit:

- NetKey
- AppKey
- DeviceKey
- QR credentials

## Development / compatibility notes

This integration currently targets Home Assistant `2026.9.0` or newer and is distributed as a HACS custom integration.

The implementation contains a minimal Bluetooth Mesh stack under `custom_components/heylight/btmesh` and uses Home Assistant's Bluetooth infrastructure for discovery and BLE connection management.

## License / attribution

MIT licensed.

Bluetooth Mesh code in `custom_components/heylight/btmesh` is derived in part from [dasimon135/ha-bluetooth-mesh](https://github.com/dasimon135/ha-bluetooth-mesh), also MIT licensed, copyright © 2026 David Simon. See `NOTICE`.
