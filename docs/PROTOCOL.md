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

The integration accepts either:

1. a Mesh Network ID advertisement matching the imported network, or
2. a valid Mesh Node Identity advertisement.

Node Identity is cryptographically checked from the imported NetKey and node unicast address rather than being accepted only from a remembered MAC address.

## Vendor model

The physical LEDs on the tested product are controlled by Telink vendor model:

`0x0211:0x0000`

The standard SIG lighting models are present but do not provide the actual physical effect control used by the HeyLight app.

## Verified power opcodes

| Operation | On-air vendor opcode |
|---|---|
| Power Set | `E0 11 02` |
| Power Get | `E1 11 02` |
| Power Status | `E3 11 02` |

Power Set parameters are:

```text
[power, productCategory]
```

where power is `0` or `1` and the tested product category byte is `0xFF`.

## Scene/effect opcode

Scene/effect Set uses:

```text
E6 11 02
```

The payload starts with:

```text
[scene, wireSpeed, ...scene-specific colour data..., productCategory]
```

HeyLight 2.3.18 uses different colour payload layouts depending on the scene.

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

The integration currently supports up to three user palette colours because that matches the tested HeyLight UI behaviour.

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

The generic HeyLight scene table contains `fallRainbow` at scene `10`, but scene 10 does not visibly activate on the tested firmware.

The tested product's working rainbow mode is:

```text
scene 45 = themeRainbowFixedcolor
```

The integration exposes this working mode under the user-facing name `fall rainbow` and sends the fixed palette:

```text
red, green, blue
```

## Effect speed conversion

HeyLight UI speed is 1–10 but the wire value is not always the same number.

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
2. white-balance multipliers approximately:
   - red: `1.0`
   - green: `0.85`
   - blue: `0.40`
3. special pure-blue handling for most scenes

This processing is necessary for the physical output to resemble the official app.

## Brightness behaviour

The APK contains a vendor brightness command using opcode `0x0211F3`, but the tested PID `0xFAC8` / firmware `51` string does not visibly respond to it.

Therefore Home Assistant brightness is implemented by scaling the RGB values used in the E6 scene payload.

The original Home Assistant colour is retained in state, so changing brightness does not permanently alter hue/saturation and returning to 100% restores the original colour.

## Connection behaviour

The integration keeps one GATT Mesh Proxy connection where possible. If it drops, it retries automatically and reconnects when the proxy can be discovered again.

A device may expose only one Mesh Proxy GATT connection at a time. This can prevent the official HeyLight app from connecting while Home Assistant is holding the proxy connection.

## Security

The QR Share Device payload contains sensitive Bluetooth Mesh credentials.

Do not publish real values for:

- NetKey / `meshPwd`
- AppKey / `meshName`
- DeviceKey / node `k`
- full Share Device QR JSON

The integration's diagnostics intentionally omit these secrets.
