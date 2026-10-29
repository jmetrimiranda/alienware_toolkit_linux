# Alienware AW720M wireless mouse: USB HID protocol notes (Linux)

Reverse-engineering notes behind the AW720M support in
[`alienware-command-center-linux/aw720m.py`](../alienware-command-center-linux/aw720m.py).
Everything here was observed on Ubuntu 24.04 (kernel 7.0) on 29 Oct 2026, through `/dev/hidraw*`,
with the mouse connected through its 2.4 GHz dongle.

> **Status:** lighting (color, effect, brightness) is **confirmed working** on the AW720M.
> Battery is read **passively** from a power notice the mouse sends on its own.
> DPI, polling rate, lift-off distance and power saving are **unknown** (they need a USB capture of
> Alienware Command Center on Windows).

Credit: the lighting commands are the **"APIv7"** protocol documented by
[alienfx-tools](https://github.com/T-Troll/alienfx-tools) (T-Troll) for the Alienware AW610M
(`0461:4ec0`). This project only confirmed that the same commands work on the AW720M and added the
power-notice decoding.

---

## 1. USB identifiers

| VID:PID | Mode | Notes |
|---|---|---|
| `413c:3029` | 2.4 GHz dongle (USB-C dongle, usually on the supplied extension) | The mode used in all tests. |
| `413c:3028` | Mouse plugged in directly with the USB-C cable | See the bluez `97-hid2hci.rules` caveat below. |

The PC used for the tests has no Bluetooth adapter, so the Bluetooth mode was not studied
(over BLE the standard Battery Service would probably expose the battery).

## 2. HID interfaces (dongle `413c:3029`)

| Interface | Usage page | Report | Role |
|---|---|---|---|
| 0 | Generic Desktop / Mouse (`05 01 09 02`) | 11 bytes: buttons, X/Y (16-bit), wheel, **5 vendor bytes (6–10)** | Pointer. Bytes 6–10 are vendor data (usage `0xF1`). |
| 1 | Keyboard | standard | Programmable buttons (macros). |
| 2 | **Vendor `0xFF00`** (`06 00 FF`) | **64 bytes IN / 64 bytes OUT, no report ID** | **Configuration channel.** Everything below goes through this interface. |

`aw720m.achar()` finds the interfaces by reading `/sys/class/hidraw/hidraw*/device/report_descriptor`:
the vendor interface descriptor starts with `06 00 FF`, the mouse interface with `05 01 09 02`.

Vendor bytes on interface 0 (passive observation): byte 6 is always `03`; byte 7 changes only on
**left click** (seemingly random value) and returns to 0. They are **not** the battery.
The DPI button reaches the host as **button 5** (bit `0x10` of the buttons byte).

## 3. Report format (interface 2)

* Every OUT report is **64 bytes**. Because the interface has no report ID, the host writes
  `0x00` (report ID) + 64 bytes to `/dev/hidrawN`; the kernel strips the leading `0x00`.
  Unused bytes are zero.
* General layout seen in both directions:

  ```
  byte 0   byte 1    byte 2       byte 3   byte 4 ...
  class    command   payload len  0x00     payload
  ```

  Host commands use class `0x40`; unsolicited device notices use class `0xC0`.
* Every command is answered with one 64-byte IN report on the same interface. The usual answer is
  the acknowledgement **`40 <cmd> 03 00 ec ac`** ("OK"); e.g. the status command returns
  `40 03 03 00 ec ac`, which carries no further information.

## 4. Commands (APIv7)

Bytes as they reach the device (report ID already removed).

| Command | Bytes | Status on AW720M |
|---|---|---|
| Status | `40 03 01 00 01` | Answers `40 03 03 00 ec ac` (ack only). Not used by alienfx-tools. |
| Set lighting | `40 10 0c 00 EF BR ZN R G B R2 G2 B2` | **Confirmed.** |
| Update / commit | `40 60 07 00 c0 4e 00 01` | Exists in the SDK; alienfx-tools does not send it to mice and it is **not needed** on the AW720M (the color changes immediately). Not sent by the app. |

### 4.1 Set lighting: `40 10 0c 00 …`

| Offset | Field | Values |
|---|---|---|
| 0–3 | header | `40 10 0c 00` (class, command `0x10`, 12-byte payload) |
| 4 | `EF` effect | see table below |
| 5 | `BR` brightness | `0`–`100` (decimal, `0x00`–`0x64`) |
| 6 | `ZN` zone | `0` or `1` (on the AW610M: 0 = main light, 1 = logo) |
| 7–9 | `R G B` | primary color |
| 10–12 | `R2 G2 B2` | secondary color (used by *morph*) |

| `EF` | Effect | Notes |
|---|---|---|
| `1` | Static | Strongest perceived color. |
| `2` | Breathing | Spends part of the cycle dim, so it looks paler. |
| `3` | Morph (transition) | Fades between color 1 and color 2. |
| `4` | Spectrum | Cycles through all colors, ignores the chosen color. |
| `5` | Pulse | Blinks the chosen color. |
| `6` | Rainbow | Saturated color wave, ignores the chosen color. |

Example, static cyan at full brightness on both zones:

```
40 10 0c 00 01 64 00 00 c9 ff 00 00 00     (zone 0)
40 10 0c 00 01 64 01 00 c9 ff 00 00 00     (zone 1)
```

The AW720M has a single RGB area (the palm logo). Which zone number drives it is still not
confirmed, so the app sends the same command to zones 0 and 1 by default ("Both").
The setting persists in the mouse until changed again.

### 4.2 "Vivid colors" (gamma correction, host side)

The LED is driven linearly, while screen colors are gamma-encoded (~2.2). Sent as-is, a pastel color
with all three channels lit (e.g. `#c061cb`) looks washed-out/whitish on the mouse. The app applies

```
c' = round(255 · (c / 255) ^ 2.2)      for each channel
```

before sending (`aw720m.corrigir_cor`), e.g. `#c061cb → #891e9a`, `#00e5ff → #00c9ff`; 0 and 255 are
unchanged. It is enabled by default and can be turned off in the UI ("Cores vivas").
For the strongest light: saturated color, static effect, brightness 100.

## 5. Power notice (battery), sent by the mouse on its own

The mouse sends this IN report on interface 2 **without being asked** when the magnetic charger is
attached or removed (observed 29 Oct 2026 during a guided test):

```
c0 0a 09 00 01 14 01 00 f7 02 13 02     charger attached
c0 0a 09 00 01 14 00 00 f8 02 13        charger removed
```

| Byte | Example | Meaning |
|---|---|---|
| 0 | `c0` | device notice class |
| 1 | `0a` | notice type: power |
| 2 | `09` | payload length |
| 3 | `00` | — |
| 4 | `01` | constant in all samples |
| 5 | `14` | **battery level in %** (0x14 = 20); probable, see open questions |
| 6 | `01` / `00` | **charger connected** (1) / not connected (0) |
| 7 | `00` | — |
| 8–9 | `f7 02` | little-endian `0x02f7` = 759: maybe voltage or a raw ADC reading |
| 10 | `13` | unknown |
| 11 | `02` | `2` = charging (absent when unplugged) |

The app keeps a second read-only file descriptor open on the vendor hidraw, decodes every `c0 0a`
notice (`aw720m.ler_energia`) and stores the last one in `logs/bateria.json`. Consequently the shown
value is the **last notice**: to refresh it, attach and detach the charger.

Other unsolicited frames seen once: pairs of `c0 07 0a …` (one ending in `b0`). They are not clicks,
wheel, DPI or charger events; meaning unknown.

## 6. Open questions

* A command that **requests** the battery level on demand (the AWCC shows it, so it travels over USB).
* Confirm that byte 5 is the percentage (check that it rises while charging).
* Which zone number (0 or 1) is the palm logo on the AW720M.
* DPI stages, polling rate, lift-off distance, sleep timer, button remapping.
* Meaning of bytes 8–10 of the power notice and of the `c0 07 0a` frames.

## 7. How to contribute: USB capture on Windows

Only commands that were **observed** in traffic from the official software should be implemented.

1. On Windows, install Wireshark with **USBPcap** and Alienware Command Center (AWCC).
2. Start a capture on the root hub where the dongle is plugged in.
3. Do **one action at a time** and write down the time: open AWCC (it reads the battery), change the
   color, change the DPI, the polling rate, the lift-off distance.
4. Filter with `usb.idVendor == 0x413c` and keep only the 64-byte interrupt OUT/IN transfers of
   interface 2 (`usb.transfer_type == 0x01 && usb.data_len == 64`).
5. Share the `.pcapng` (or the hex dumps) in an issue, together with the list of actions.
   The parser in [`tools/ler_pcap_usbpcap.py`](../tools/ler_pcap_usbpcap.py) reads the file offline
   (`python3 tools/ler_pcap_usbpcap.py capture.pcapng --todos` also lists interrupt transfers).

Passive tools on Linux (no writes): `python3 tools/sondar.py escutar 60` (listen on interface 2),
`python3 tools/sondar.py extras 20` (vendor bytes of interface 0) and `tools/teste_guiado.sh`
(guided test that asks you to click, scroll, press DPI and attach the charger).

## 8. Safety rules

* **Never sweep or fuzz command bytes.** Unknown commands can change settings stored in the mouse or
  the dongle, or trigger the bootloader. First listen passively, then send only documented or captured
  commands.
* **Never touch firmware.** Dell warns that an interrupted update can brick the mouse or the dongle;
  use AWCC on Windows for firmware.
* Opening the vendor interface needs a udev rule (`TAG+="uaccess"` for `413c:3028|3029`), installed by
  `./install.sh` from [`udev/70-alienware-toolkit.rules`](../udev/70-alienware-toolkit.rules).

## 9. Known Linux caveat: wired mode (`413c:3028`)

bluez ships `97-hid2hci.rules`, which can switch off the mouse when it is plugged in with the cable
(bluez issue #2680). Workaround: copy `/usr/lib/udev/rules.d/97-hid2hci.rules` to
`/etc/udev/rules.d/` and add `ATTRS{product}!="*AW720M*"` to the Dell line.

The kernel does not create a `power_supply` for the mouse (it does not use the standard HID
*Battery Strength* usage), so `upower` and the GNOME battery menu do not show it.
