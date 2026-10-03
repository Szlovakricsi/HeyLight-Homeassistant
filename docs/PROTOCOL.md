# HeyLight / Telink protocol notes

This document records the protocol details currently verified by the HeyLight Home Assistant integration.

## Scope

The implementation has been physically tested with a HeyLight / Telink Bluetooth SIG Mesh RGB light string using:

- Company ID: `0x0211`
- Vendor model: `0x0211:0x0000`
- Product ID: `0xFAC8`
- firmware label: `51`
- HeyLight family/agent: `sl2c0030`

These notes are product-specific where stated. Other HeyLight/Telink products may use different scene IDs or payload layouts.

## Share Device QR mapping

The HeyLight Share Device QR contains all information needed to join an already-provisioned mesh.

For the tested family:

- `meshPwd` ASCII bytes are used as the Bluetooth Mesh NetKey
- `meshName` ASCII bytes are used as the Bluetooth Mesh AppKey
- node `a` is the unicast address
- node `k` is the DeviceKey
- node `m` is the Bluetooth MAC address
- node `t` is the product type / PID
- node `p.l` is the advertised light/address count used by the speed conversion logic

The opaque node `i` field contains composition information, including company/product/version information and model lists.

## Mesh Proxy discovery

Provisioned devices advertise Bluetooth Mesh Proxy service UUID `0x1828`.

The integration accepts either the correct Mesh Network ID advertisement or a valid Mesh Node Identity advertisement. Node Identity is cryptographically checked from the imported NetKey and node unicast address.

## Vendor model

The physical LEDs on the tested product are controlled by Telink vendor model `0x0211:0x0000`.

The standard SIG lighting models are present but do not provide the physical effect control used by the HeyLight app.

## Verified power opcodes

| Operation | On-air vendor opcode |
|---|---|
| Power Set | `E0 11 02` |
| Power Get | `E1 11 02` |
| Power Status | `E3 11 02` |

Power Set parameters are `[power, productCategory]`, where power is `0` or `1` and the tested product category byte is `0xFF`.

## Scene/effect opcode

Scene/effect Set uses `E6 11 02`.

The payload starts with `[scene, wireSpeed, ...scene-specific colour data..., productCategory]`.

### Single-colour layout

```text
[scene, speed, 1, 0, R, G, B, productCategory]
```

### Dual-colour layout

```text
[scene, speed, 2,
 0, R1, G1, B1,
 0, R2, G2, B2,
 productCategory]
```

### Multi-colour layout

```text
[scene, speed, count,
 0, R1, G1, B1,
 0, R2, G2, B2,
 0, R3, G3, B3,
 productCategory]
```

## Verified effect map for PID 0xFAC8 / firmware 51

| Home Assistant effect | Scene | Colour behaviour |
|---|---:|---|
| normal | 0 | 1 user colour |
| flick | 1 | 1 user colour |
| flick around | 3 | 1 user colour |
| random color | 5 | internal/fixed |
| fading | 6 | 1 user colour |
| fading adv | 7 | up to 3 user colours |
| color change1 | 8 | up to 3 user colours |
| color change2 | 9 | up to 3 user colours |
| fall rainbow | 45 | internal/fixed RGB palette |
| fall snake | 11 | up to 3 user colours |
| fall ant | 12 | up to 3 user colours |
| moon beyond stars | 13 | 2 user colours |
| collide | 18 | 1 user colour |
| little fire | 19 | up to 3 user colours |
| random breath | 21 | 2 user colours |
| wave down | 22 | up to 3 user colours |
| flag | 23 | up to 3 user colours |
| heap up | 24 | 1 user colour |
| vertical wave | 25 | up to 3 user colours |
| snake | 26 | 2 user colours |
| wave up | 27 | up to 3 user colours |

### Rainbow scene detail

The generic HeyLight scene table contains `fallRainbow` at scene `10`, but scene 10 does not visibly activate on the tested firmware. The working product-specific rainbow mode is scene `45` (`themeRainbowFixedcolor`), using a fixed red/green/blue palette.

## Effect speed conversion

For scenes `{1, 3, 5, 8, 9}`:

```text
wireSpeed = 11 - uiSpeed
```

For the tested 200-position product, other supported scenes use:

| UI speed | Signed delay | Wire byte |
|---:|---:|---:|
| 1 | 4 | 4 |
| 2 | 3 | 3 |
| 3 | 2 | 2 |
| 4 | 1 | 1 |
| 5 | -1 | 255 |
| 6 | -2 | 254 |
| 7 | -3 | 253 |
| 8 | -4 | 252 |
| 9 | -5 | 251 |
| 10 | -6 | 250 |

## Colour processing

Before RGB values are sent to the controller, the integration mirrors HeyLight's observed colour processing:

1. 256-entry gamma lookup
2. white-balance multipliers approximately red `1.0`, green `0.85`, blue `0.40`
3. special pure-blue handling for most scenes

## Brightness behaviour

The APK contains vendor brightness opcode `0x0211F3`, but the tested PID `0xFAC8` / firmware `51` string does not visibly respond to it. Home Assistant brightness is therefore implemented by scaling the RGB values used in the E6 scene payload while preserving the original Home Assistant colour state.

## Device-side timing / Bluetooth Mesh Scheduler

The HeyLight 2.3.18 APK's Timing screen uses the standard Bluetooth Mesh Scheduler models rather than a HeyLight vendor command. The tested node composition includes:

- Scheduler Server `0x1206`
- Scheduler Setup Server `0x1207`

The app exposes exactly four controls:

- Timing switch
- Repeat
- Turn on time
- Turn off time

The app uses two schedule entries:

- entry/index `1`: turn on
- entry/index `2`: turn off

Scheduler message opcodes used by the integration are:

| Message | Opcode |
|---|---|
| Scheduler Action Get | `0x8248` |
| Scheduler Action Set | `0x60` |
| Scheduler Action Status | `0x5F` |

The 80-bit Scheduler Action payload is packed in Bluetooth Mesh field order:

```text
Index(4)
Year(7)
Month(12)
Day(5)
Hour(5)
Minute(6)
Second(6)
DayOfWeek(7)
Action(4)
TransitionTime(8)
SceneNumber(16)
```

HeyLight 2.3.18 uses these values for the tested Timing UI:

- `Year = 0x64` (any year)
- `Second = 0`
- `TransitionTime = 0`
- `SceneNumber = 0`
- Timing ON: action `1` for entry 1 and action `0` for entry 2
- Timing OFF: action `0xF` (No Action) for both entries
- Repeat ON: month mask `0xFFF`, day `0`, weekday mask `0x7F`
- Repeat OFF: current month bit only, current day, weekday mask `0`

This intentionally mirrors the app's packet construction instead of replacing it with Home Assistant automations. The resulting Configuration entities write directly to the light string's own scheduler.

## Connection behaviour

The integration keeps one GATT Mesh Proxy connection where possible. If it drops, it retries automatically and reconnects when the proxy can be discovered again.

A device may expose only one Mesh Proxy GATT connection at a time. This can prevent the official HeyLight app from connecting while Home Assistant holds the proxy connection.

## Security

The QR Share Device payload contains sensitive Bluetooth Mesh credentials. Do not publish real NetKey, AppKey, DeviceKey or Share Device QR JSON values. Diagnostics intentionally omit these secrets.
