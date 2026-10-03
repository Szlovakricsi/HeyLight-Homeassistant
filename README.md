# HeyLight Home Assistant

Standalone Home Assistant integration for selected **HeyLight / Telink Bluetooth SIG Mesh**
RGB light strings.

> Experimental interoperability project. Not affiliated with Heylight, Telink,
> DekorTrend, or Home Assistant.

## Features

- Fully local Bluetooth Mesh control through Home Assistant's Bluetooth stack
- No Heylight cloud required after importing the mesh
- First-run setup directly from the Heylight **Share Device QR code**
  - upload a QR image, **or**
  - paste the decoded QR JSON text
- Power on/off
- RGB effect color
- Effect selector
- Effect speed (1–10)
- Optional second and third effect colors
- HACS-compatible custom repository layout

### Effects currently mapped

`normal`, `flick`, `flick around`, `random color`, `fading`, `fading adv`,
`color change1`, `color change2`, `fall rainbow`, `fall snake`, `fall ant`,
`moon beyond stars`, `collide`, `little fire`, `random breath`, `wave up`,
`wave down`, `flag`, `head up`, `vertical wave`, `snake`.

For `normal`, only color 1 is used. For effects, color 2 and color 3 are
separate RGB helper entities. Turn them on to include those palette slots;
leave them off to run the effect with one color.

## Supported/tested device

Initial implementation is based on a HeyLight string using:

- Bluetooth SIG Mesh / Telink
- Company ID `0x0211`
- Vendor model `0x0211:0x0000`
- Product ID `0xFAC8`
- Heylight `sl2c0030` family

Other HeyLight Telink devices with the same vendor model may work, but are not
yet verified.

## Install with HACS

1. HACS → Integrations → `⋮` → **Custom repositories**
2. Add:
   `https://github.com/Szlovakricsi/HeyLight-Homeassistant`
3. Category: **Integration**
4. Install **HeyLight**
5. Restart Home Assistant
6. Settings → Devices & services → Add integration → **HeyLight**

## Configure from the QR code

In the Heylight app, use **Share Device** and display the QR code.

At setup you can either:

- upload a screenshot/photo of the QR, or
- paste the decoded QR text.

The text has this general shape (secrets intentionally replaced):

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

**Never post your real QR JSON publicly.** It contains the Bluetooth Mesh
network/application/device key material.

## Bluetooth behavior

The tested controller advertises **Mesh Proxy Node Identity** after provisioning.
The integration therefore accepts:

- the correct Mesh Network ID advertisement when present, or
- Node Identity from a Bluetooth address explicitly contained in the imported
  Heylight Share Device QR.

The controller may expose only one GATT Mesh Proxy connection at a time. While
Home Assistant holds that connection, the Heylight mobile app may be unable to
connect to the same controller.

## Vendor protocol

The tested string exposes standard SIG lighting models, but its physical LEDs
are driven by the Telink vendor model. This integration uses the verified
vendor path:

- power Set: `E0 11 02`
- power Get: `E1 11 02`
- power Status: `E3 11 02`
- scene/effect Set: `E6 11 02`

Color gamma/white-balance processing and effect-speed conversion mirror the
behavior observed in Heylight 2.3.18 for the tested product family.

## Privacy

The imported Share Device JSON is stored in the Home Assistant config entry.
It is not sent to this project's GitHub repository or to a cloud service.
Diagnostics intentionally omit NetKey, AppKey and DeviceKey values.

## License / attribution

MIT licensed. Bluetooth Mesh code in `custom_components/heylight/btmesh` is
derived in part from
[dasimon135/ha-bluetooth-mesh](https://github.com/dasimon135/ha-bluetooth-mesh),
also MIT licensed, copyright © 2026 David Simon. See `NOTICE`.
