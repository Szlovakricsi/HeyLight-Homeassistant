# HeyLight Home Assistant

Standalone Home Assistant integration for selected **HeyLight / Telink Bluetooth SIG Mesh** RGB light strings.

> Experimental interoperability project. Not affiliated with Heylight, Telink, DekorTrend, or Home Assistant.

## Features

- Fully local Bluetooth Mesh control through Home Assistant's Bluetooth stack
- No Heylight cloud required after importing the mesh
- First-run setup directly from the Heylight **Share Device QR code**
  - upload a QR image, or
  - paste the decoded QR JSON text
- Power on/off
- RGB effect colour
- Brightness control
- Effect selector
- Effect speed (1–10)
- Optional second and third effect colours where supported
- Automatic Bluetooth reconnect
- Device-side **Timing** configuration using the Bluetooth Mesh Scheduler model
- HACS-compatible custom repository layout

## Supported/tested device

Initial implementation is physically tested with a HeyLight string using:

- Bluetooth SIG Mesh / Telink
- Company ID `0x0211`
- Vendor model `0x0211:0x0000`
- Product ID `0xFAC8`
- firmware label `51`
- Heylight `sl2c0030` family

Other HeyLight Telink devices with the same vendor model may work, but are not yet verified.

## Install with HACS

1. HACS → Integrations → `⋮` → **Custom repositories**
2. Add `https://github.com/Szlovakricsi/HeyLight-Homeassistant`
3. Category: **Integration**
4. Install **HeyLight**
5. Restart Home Assistant
6. Settings → Devices & services → Add integration → **HeyLight**

## Configure from the QR code

In the Heylight app, use **Share Device** and display the QR code.

At setup you can either upload a screenshot/photo of the QR or paste the decoded QR text.

Example with secrets replaced:

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

**Never post your real QR JSON publicly.** It contains Bluetooth Mesh network/application/device key material.

## Entities

The main light entity provides power, RGB colour, brightness and effect selection. `Effect speed` is exposed as a Number entity. Effects that support extra colours expose `Effect color 2` and `Effect color 3` helper light entities.

Configuration entities are shown in the device's **Configuration** section when the Scheduler Server/Setup Server models are present:

- `Timing` — enables/disables the device-side timer
- `Timing repeat` — matches the Heylight app's Repeat switch
- `Turn on time` — device-side power-on time
- `Turn off time` — device-side power-off time

These controls are stored in the light string itself, not as Home Assistant automations. The implementation intentionally mirrors the official Heylight 2.3.18 Timing screen: Scheduler slot 1 turns the string on and slot 2 turns it off. Repeat ON uses all seven weekdays. Repeat OFF uses the current month/day, matching the app's packet construction.

## Verified effect map

| Effect | Colour controls |
|---|---|
| normal | 1 colour |
| flick | 1 colour |
| flick around | 1 colour |
| random color | none; internal colours |
| fading | 1 colour |
| fading adv | up to 3 colours |
| color change1 | up to 3 colours |
| color change2 | up to 3 colours |
| fall rainbow | none; fixed internal rainbow |
| fall snake | up to 3 colours |
| fall ant | up to 3 colours |
| moon beyond stars | 2 colours |
| collide | 1 colour |
| little fire | up to 3 colours |
| random breath | 2 colours |
| wave down | up to 3 colours |
| flag | up to 3 colours |
| heap up | 1 colour |
| vertical wave | up to 3 colours |
| snake | 2 colours |
| wave up | up to 3 colours |

`fall rainbow` maps to the working product-specific scene 45 (`themeRainbowFixedcolor`) on PID `0xFAC8` / firmware `51`.

## Brightness

The tested firmware does not visibly react to Heylight's standalone vendor brightness opcode. Home Assistant brightness therefore scales the scene RGB values before transmission while preserving the original selected colours in Home Assistant state.

## Bluetooth behavior

The integration accepts the correct Mesh Network ID advertisement or a cryptographically valid Mesh Node Identity advertisement derived from the imported NetKey and node unicast address.

It keeps a Mesh Proxy GATT connection where possible and reconnects automatically after a disconnect. A controller may expose only one GATT Mesh Proxy connection at a time, so the official Heylight app may be unable to connect while Home Assistant holds it.

## Protocol documentation

See [`docs/PROTOCOL.md`](docs/PROTOCOL.md) for the reverse-engineered Telink vendor commands, effect payload layouts, speed conversion and Bluetooth Mesh Scheduler details.

## Privacy

The imported Share Device JSON is stored in the Home Assistant config entry. It is not sent to this project's GitHub repository or to a cloud service. Diagnostics intentionally omit NetKey, AppKey and DeviceKey values.

## License / attribution

MIT licensed. Bluetooth Mesh code in `custom_components/heylight/btmesh` is derived in part from [dasimon135/ha-bluetooth-mesh](https://github.com/dasimon135/ha-bluetooth-mesh), also MIT licensed, copyright © 2026 David Simon. See `NOTICE`.