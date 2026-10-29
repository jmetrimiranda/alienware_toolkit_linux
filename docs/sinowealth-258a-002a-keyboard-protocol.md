# Redragon K617 Fizz Rainbow / SINO WEALTH "Gaming KB" (USB 258a:002a): keyboard protocol notes

*Alienware Toolkit for Linux, 2026-10-29. Unit under test: the keyboard plugged into jorgemetri-H110 (USB port 1-3, bcdDevice 12.09), later identified as a **Redragon K617 Fizz Rainbow (K617-R-B)** (see the next section).*

## TL;DR

| Question | Answer | Confidence |
|---|---|---|
| Controller family | Sinowealth 8051 keyboard MCU, very likely **BYK901 (SH68F90A)**: our interface 0 and interface 1 HID report descriptors are byte-for-byte identical to the DK200 keyboard (BYK901) captured in OpenRGB issue #1804. | High |
| Is `258a:002a` one product? | **No.** It is a generic Sinowealth PID reused by many brands and *different firmwares* (e.g. AJAZZ AK510 uses the same PID with a completely different report layout). The PID alone does not identify the protocol. | High |
| Read path | `GET_FEATURE` of reports 5, 9, 10, 11, 12 on interface 1. Standard HID GET_REPORT, no side effects. | High |
| Write path (color, effect, brightness, speed, direction, per-key) | **Unknown. No trustworthy public source exists for this report layout.** Nothing was written to the device. | High (that it is unknown) |
| Report 5 | Doubles as the **ISP/bootloader command channel** on interface 1 for SH68F90 boards (`05 75 00 00 00 00` reboots into ISP). Never write to it by guesswork. | High |
| Polling rate | 1000 Hz (interrupt endpoints 0x81/0x82, bInterval = 1 ms, full speed). No known command to change it. | High (value) |
| Report 9 size | **504 bytes** (`96 f8 01` = 0x01F8), not 1016 as first assumed. | High |

**Decision taken (project safety rule):** without a confirmed write protocol, the toolkit ships *read-only* support: device detection, safe reads, backups, byte diffs, a lighting *preview* page and this capture plan. All `definir_*` functions in `teclado_sinowealth.py` refuse to send anything, and writes to report 5 are blocked unconditionally.

## Identified model: Redragon K617 Fizz Rainbow (K617-R-B)

The keyboard that enumerates as `SINO WEALTH "Gaming KB "` (`258a:002a`) on this machine is a
**Redragon K617 Fizz Rainbow**, model **K617-R-B** (R = Rainbow backlight, B = black body).

| Item | K617 Fizz **Rainbow** (this unit) | K617 Fizz **RGB** (other revision) |
|---|---|---|
| USB ID | `258a:002a` | `258a:0049` |
| Layout | 60 %, 61 keys, US ANSI | 60 %, 61 keys, US ANSI |
| Backlight | **Fixed factory colour per row** (rainbow stripes: red, orange/yellow, green, cyan/blue, purple). Only the **mode, brightness and speed** change, with the Fn keys. | Full RGB, colour chosen per mode (Fn + Space) or by software. |
| HID layout | Interface 1 feature reports 5 (5 B), 9 (**504 B**), 10 (41 B), 11 (126 B), 12 (**1920 B**); NKRO input report 6 | Different descriptor |
| Linux lighting control | **None known** (this document) | Third-party tool: [fizz-rgb](https://github.com/MrSchrodingers/fizz-rgb) by MrSchrodingers (MIT), also on PyPI as `fizzctl` |

What this means in practice:

* **On the Rainbow revision the LED colours are fixed in hardware.** Linux cannot change the colour of
  a key: the most a host protocol could do is what the Fn keys already do (mode, brightness, speed).
  Quick test to tell the revisions apart: press **Fn + Space**. On the RGB revision the Space key
  starts flashing through the colours (colour-selection mode); on the Rainbow nothing happens.
* **If you own the K617 Fizz RGB (`258a:0049`)**, use [fizz-rgb](https://github.com/MrSchrodingers/fizz-rgb):
  it targets that ID and is the right reference. Do **not** send its commands to `258a:002a`: the
  descriptor is different and report 5 here is also the bootloader channel (§3.3).
* **What the toolkit does for the Rainbow:** a read-only page titled *REDRAGON K617 FIZZ │ RAINBOW*
  with a 3D preview (60 % layout, black body, the factory row colours and preview-only effects), the
  table of Fn shortcuts from the K617 manual (some RGB-only combinations may not exist on the Rainbow)
  and the safe diagnostics described below. There is **no APPLY button for colour**.
* **What is missing for real control (mode/brightness/speed from Linux):** a USB capture of the
  official Redragon software on Windows (Wireshark + USBPcap, one action per file, plan in §6), if
  Redragon ships software for this revision at all. **Contributions are welcome**: open an issue with
  the `.pcapng` files and the list of actions.
* **Privacy:** interface 1 also carries the NKRO key bitmap (report 6). Granting the user access to it
  means any program in the session could read keystrokes from that node. That is why the main udev
  rule ([`udev/70-alienware-toolkit.rules`](../udev/70-alienware-toolkit.rules)) covers **only the mouse
  and the headset**; the keyboard is in the optional
  [`udev/71-sinowealth-keyboard-optional.rules`](../udev/71-sinowealth-keyboard-optional.rules),
  installed only with `./install.sh --keyboard-experimental` (with an explicit warning). The toolkit
  never reads the input stream, and interface 0 (boot keyboard) is never opened.
* **Report 5 = bootloader channel: never write to it** (§3.3). The toolkit blocks every write to it.

Fn shortcuts (from the K617 Fizz RGB manual; the app shows the same table in the *Atalhos Fn* tab,
source in [`alienware-command-center-linux/k617_atalhos.py`](../alienware-command-center-linux/k617_atalhos.py)):

| Keys | Function | On the Rainbow |
|---|---|---|
| Fn + Right Alt | Next lighting mode (cycle; the RGB manual lists 11 modes) | yes |
| Fn + M | Brightness, 5 levels | yes |
| Fn + , | Effect speed, 5 levels | yes |
| Fn + Space | Colour-selection mode | **no** (RGB only; use it as the test) |
| Fn + Win | Lock / unlock the Windows key | yes |
| Fn + Esc (hold 3 s) | Factory reset | probably |
| Fn + 1 … 0, -, = | F1 … F12 | yes |
| Fn + W / A / S / D | Arrow keys ↑ ← ↓ → | yes |
| Fn + [ / ] | Insert / Delete | probably |
| Fn + ; / ' | Home / End | probably |
| Fn + . / / | Page Up / Page Down | probably |

## 1. The device

From sysfs ([`data/keyboard-usb-sysfs.txt`](data/keyboard-usb-sysfs.txt)):

```
idVendor=258a idProduct=002a bcdDevice=1209 manufacturer="SINO WEALTH" product="Gaming KB "
USB 1.10, 12 Mb/s (full speed), bMaxPower 500 mA
interface 0: ep 0x81 interrupt IN, 8 bytes, bInterval 1 ms   -> boot keyboard
interface 1: ep 0x82 interrupt IN, 16 bytes, bInterval 1 ms  -> everything else
```

### Interface 1 report descriptor (269 bytes, [`data/descritor-interface1.hex`](data/descritor-interface1.hex))

| Report ID | Type | Usage | Size | Notes |
|---|---|---|---|---|
| 1 | Input | Generic Desktop / System Control (0x80), usages 0x81–0x83 | 3 bits + 5 pad | Power / Sleep / Wake |
| 2 | Input | Consumer Control, usage 0x000–0x23C | 16 bits | Media keys |
| 5 | Feature | Vendor 0xFF00, usages 1–2 | **5 bytes** (6 with ID) | Short command report. Also the ISP channel (see §3.3). |
| 6 | Input | Keyboard bitmap, usages 0x04–0x70 | 120 bits | NKRO key bitmap |
| 9 | Feature | Vendor 0xFF00 | **504 bytes** | Large block |
| 10 | Feature | Vendor 0xFF00 | **41 bytes** | Medium block |
| 11 | Feature | Vendor 0xFF00 | **126 bytes** | Medium block (126 = 42 × 3) |
| 13 | Input | Mouse: 5 buttons, X/Y 16-bit, wheel, AC Pan | 7 bytes | Used by macros; the "spurious mouse" in kernel reports |
| 12 | Feature | Vendor 0xFF00 | **1920 bytes** | Largest block (1920 = 640 × 3 = 128 × 15) |

Note: the descriptor quoted in the original task was truncated after report 13 and therefore missed report 12; report 9 is 504 bytes, not 1016.

Interface 0 (67 bytes, [`data/descritor-interface0.hex`](data/descritor-interface0.hex)) is a plain boot keyboard: 8-byte input report and a 5-bit LED output report (Num/Caps/Scroll/Compose/Kana).

## 2. Family and brands

**Identical descriptor = same firmware family.** OpenRGB issue #1804 ("Dk200 Generic Keyboard", Shenzhen Langao, MCU marked **BYK901-00001**, resold as VictSing TKL and others) attached `dk200.plugin.pcapng`. Parsing that capture ([`tools/ler_pcap_usbpcap.py`](../tools/ler_pcap_usbpcap.py), output in [`data/keyboard-descriptors-from-openrgb-captures.txt`](data/keyboard-descriptors-from-openrgb-captures.txt)) gives interface 0 and interface 1 report descriptors that are **byte-for-byte identical** to ours. The DK200 reported bcdDevice 34.25 vs our 12.09 (different build/board, same HID layout). The DK200 issue has no OEM software ("No software came with the device") and the capture only shows enumeration and Fn-key lighting changes, i.e. no host lighting commands.

BYK901 = Sinowealth **SH68F90A** (8051), per the SMK project (`docs/keyboards/eyooso-z11.md`: "MCU: BYK901(-0997A) (SH68F90A)") and community notes.

Keyboards reported with USB `258a:002a` (not all share our layout):

| Product | Source | Layout known? |
|---|---|---|
| DK200 / VictSing TKL (Shenzhen Langao, BYK901) | OpenRGB #1804 | **Identical to ours** |
| EWEADN TK100 (BYK901) | OpenRGB #5006 (IDs only) | Likely same MCU, unverified |
| E-YOOSO Z11 (BYK901/SH68F90A, single-colour) | SMK, sinowealth-kb-tool `eyooso-z11` | Unverified |
| Redragon K630 (non-RGB), Xinmeng XM-RF68 | sinowealth-kb-tool device specs | Unverified |
| AJAZZ AK510 Retro | OpenRGB #762 (captures) | **Different**: report 5 + report 6 (1031 bytes) |
| Hexgears GK715, HATOR Starfall Rainbow | linux-hardware.org comments | Unverified |
| HAVIT KB487L | brave-browser issue #57772 | Unverified |
| Machenike K500 | linux-input regression report (2026-06) | Unverified |

## 3. Protocol: what is and is not known

### 3.1 Reading (safe)

`HIDIOCGFEATURE` on `/dev/hidrawN` (interface 1) for report IDs 5, 9, 10, 11 and 12. This is a USB control `GET_REPORT(Feature)`; it does not change device state. `teclado_sinowealth.ler_config()` (in `alienware-command-center-linux/`) opens the node **read-only** (`O_RDONLY`) and only issues these ioctls. The input stream (keys, report 6) is never read.

Results on this unit: see §4.

### 3.2 Writing: no trustworthy source

* **OpenRGB** (master `aac7e551`, 2026-10-27): no detector for PID 0x002A. `SinowealthControllerDetect.cpp` keeps the generic Sinowealth keyboard detectors (FL Esports F11 0x0049, "RGB keyboard" 0x0016) **commented out** with the note *"Sinowealth keyboards are disabled due to VID/PID pairs being reused from Redragon keyboards, which ended up in bricking the latter"*. RFC #5951 (2026-10-08) lists the PID conflicts and bricked models (Redragon K618 and K621 "bricked by F11 code").
* **Related protocols that do NOT match this layout** (and must not be tried):

| Protocol | Reports | Why it does not apply |
|---|---|---|
| Classic Sinowealth keyboard (FL Esports F11, Zuoya X51 0x0016, GK850W, AJAZZ AK510 with 002A) | cmd report 5 (6 B) + data report 6 (1032 B); read-modify-write `SET 05 83 …` → `GET 06` → `SET 06 03 …` (seen in the AK510 captures) | Our report 6 is an NKRO *input* report; there is no 1032-byte feature report. |
| Genesis Thor 300 (0x0090) | report 0x0A, 8 bytes: `0a 03 01`, `0a 0a mode bright speed color`, `0a 0c 01 key r g b` | Our report 10 is 41 bytes. Same ID, different size, unknown semantics. |
| Sinowealth 0x010C keyboards | report 6, 520 bytes | Not present here. |
| Redragon KS82-B (0x0049, Sinodragon) | report 8, 382 bytes | Not present here. |
| libratbag Sinowealth mice | reports 4/5/6 | Mice, different layout. |

* Searches (OpenRGB issues API, GitHub/Exa/Tavily, SignalRGB public plugins, linux-hardware.org) found no code or capture that sends lighting commands to the 5/9/10/11/12 layout.

### 3.3 Report 5 is also the bootloader channel (danger)

`sinowealth-kb-tool` (master `242f7921`, 2026-10-23) lists three `258a:002a` devices (E-YOOSO Z11, Redragon K630 no-RGB, Xinmeng XM-RF68) on `DEVICE_BASE_SH68F90`, whose ISP access is **interface 1, report ID 5**. Its device selector sends `[0x05, 0x75, 0, 0, 0, 0]` (`CMD_ISP_MODE`) to reboot the keyboard into the ISP bootloader; in ISP mode report 5 carries `0x55` enable firmware, `0x52` init read, `0x57` init write, `0x45` erase, `0x5A` reboot. libratbag's Sinowealth mouse driver also documents command `0x75` as "puts the device into DFU mode". A wrong byte in report 5 can therefore leave the keyboard in bootloader mode or worse. `teclado_sinowealth.verificar_escrita()` rejects **every** write to report 5, with these bytes named explicitly.

### 3.4 Settings

* **Polling rate:** 1000 Hz (bInterval 1 ms on both interrupt endpoints). Reported read-only; no command to change it is known.
* **NKRO:** supported by the descriptor (report 6, 120-bit bitmap). How the firmware switches 6KRO/NKRO (usually an Fn combo) is not known over USB.
* **Mouse report 13:** used by the firmware for mouse macros. A 2026 linux-input regression report describes a Machenike K500 (`258a:002a`) whose short report-13 packets cause a stuck Shift on kernels with the new zero-padding path (7.0.8-zen and later). Not observed here; listed for troubleshooting.

## 4. Byte map of the reads on this unit

*Status (2026-10-29): **not read yet.** The reads need access to interface 1. During development the installed rule was an old version (`IMPORT{builtin}="usb_id"` + `ENV{ID_USB_INTERFACE_NUM}=="01"`) that never tagged the keyboard's hidraw node. The fixed two-step rule (`KERNELS=="*:1.1"` then `ATTRS{idVendor}=="258a"`) is now the optional [`udev/71-sinowealth-keyboard-optional.rules`](../udev/71-sinowealth-keyboard-optional.rules), installed only with `./install.sh --keyboard-experimental` (read the privacy note first).*

What is already known without opening the device:

| Report | Bytes | Size factorisations | Working hypothesis |
|---|---|---|---|
| 5 | 5 | — | Short command/status. ISP channel: never written. |
| 9 | 504 | 126 × 4, 168 × 3, 8 × 63 | Key map / macro table (4 bytes per key slot is common for Sinowealth key remaps). |
| 10 | 41 | 1 + 40 | Global lighting settings (mode, brightness, speed, direction, colour). |
| 11 | 126 | 42 × 3, 126 × 1 | Colour palette or per-key-slot table (126 slots also appear in the KS82-B per-key frame). |
| 12 | 1920 | 640 × 3, 128 × 15, 5 × 384 | Per-key RGB frames for custom modes. |

**How to fill this section (zero writes):**

```bash
./install.sh --keyboard-experimental        # optional rule for interface 1 (privacy warning)
python3 tools/sondar_teclado.py backup       # reads 5, 9, 10, 11, 12 twice -> dados/backup-*.json + .bin
# change ONE thing with the keyboard's Fn keys (e.g. Fn + Right Alt = next mode), then:
python3 tools/sondar_teclado.py ler depois-efeito
python3 tools/sondar_teclado.py comparar dados/backup-*.json dados/depois-efeito-*.json
```

Repeat for brightness (Fn + M) and speed (Fn + ,). On the Rainbow there is no colour to change. Each diff tells which byte of which report stores that setting.

## 5. Implementation in the toolkit

| File | Role |
|---|---|
| [`alienware-command-center-linux/teclado_sinowealth.py`](../alienware-command-center-linux/teclado_sinowealth.py) | `achar()` (sysfs only), `ler_config()` (GET_FEATURE, read-only fd), `salvar_leitura()`, `interpretar_config()`, `comparar()`, the guarded `definir_efeito/cor/brilho/velocidade/direcao/cor_por_tecla()` and `restaurar()`. Writes need `PROTOCOLO_CONFIRMADO = True` **and** an entry in `COMANDOS` built from a capture; report 5 is never written. |
| [`alienware-command-center-linux/ui/pagina_teclado.py`](../alienware-command-center-linux/ui/pagina_teclado.py) | GTK4 page *REDRAGON K617 FIZZ │ RAINBOW*: 3D preview (60 % layout, black body, fixed row colours, preview-only effects), Fn shortcuts table and read-only diagnostics. No APPLY button for colour. |
| [`alienware-command-center-linux/k617_atalhos.py`](../alienware-command-center-linux/k617_atalhos.py) | Fn shortcut table (from the K617 manual) used by the page. |
| [`tools/sondar_teclado.py`](../tools/sondar_teclado.py) | CLI: `info`, `ler [label]`, `backup`, `comparar A.json B.json`. |
| [`tools/ler_pcap_usbpcap.py`](../tools/ler_pcap_usbpcap.py) | Stdlib-only USBPcap `.pcapng` reader: SET_REPORT / GET_REPORT / HID report descriptors. |

**Privacy note:** the optional udev rule (`udev/71-sinowealth-keyboard-optional.rules`) grants the logged-in user access to interface 1. Interface 1 also carries the NKRO key bitmap (report 6), so any process in the user session can read keystrokes from that node when the keyboard is in NKRO mode. The toolkit never reads the input stream; if this matters, restrict the rule to a dedicated group instead of `uaccess`.

## 6. Windows capture plan (USBPcap + official software)

Goal: obtain the real write commands for *this* layout, then enable them one by one.

1. **Identify the product.** Here it is a Redragon K617 Fizz Rainbow (K617-R-B): get Redragon's Windows software for the K617, if one exists for the Rainbow revision. Generic BYK901 boards often ship with a "Gaming Keyboard"/"RGB Keyboard" OEM tool. If no software exists for this model, stop here: the lighting stays on the Fn keys.
2. **Setup on the Alienware Area-51:** install Wireshark with the USBPcap option; plug the keyboard directly into the PC (no hub); open the USBPcap interface that shows `258a:002a`.
3. **Record one action per file**, naming files after the action. Start the capture before the software opens:
   * `00-open-software.pcapng` (startup reads), `01-static-red`, `02-static-green`, `03-static-blue`, `04-static-white`;
   * one file per effect (all built-in modes, including off);
   * `brightness-0` … `brightness-4`, `speed-0` … `speed-4`, `direction-left`, `direction-right`;
   * `perkey-esc-red`, `perkey-w-green` (one key at a time), then `perkey-all-blue`;
   * polling rate / NKRO / Win-lock toggles if the software exposes them;
   * `99-close-software`.
   **Never** click firmware update, "upgrade", "reset/restore factory" or anything mentioning boot/ISP during the session.
4. **Filters:** `usb.idVendor == 0x258a` to find the device address, then `usb.device_address == N && usb.setup.bRequest == 0x09` (SET_REPORT) and `== 0x01` (GET_REPORT).
5. **Bring the `.pcapng` files to `~/lab`** and run `python3 -I tools/ler_pcap_usbpcap.py file.pcapng`. Diff consecutive captures to explain each byte.
6. **Acceptance criteria before any write on Linux:**
   * the capture's interface 1 descriptor equals `DESCRITOR_FAMILIA` (269 bytes);
   * every byte of the command is explained by the diffs (no "magic" bytes left);
   * no SET_REPORT to report 5 other than ones seen in the capture, and never `0x75` / ISP bytes;
   * first Linux test = one static colour, with `tools/sondar_teclado.py backup` before and a restore of the original effect afterwards.
7. Then fill `COMANDOS` in `alienware-command-center-linux/teclado_sinowealth.py`, set `PROTOCOLO_CONFIRMADO = True`, and the APPLY button comes alive.

**Linux-only complement (zero writes):** change the lighting with the keyboard's own Fn keys and diff reads (`tools/sondar_teclado.py ler antes` → Fn change → `ler depois` → `comparar`). This maps which stored bytes hold mode, brightness, speed and colour, and speeds up the capture analysis, but it does not prove that a SET_FEATURE on the same report is the write path, nor whether it writes flash.

## 7. Confidence summary

| Claim | Confidence | Basis |
|---|---|---|
| Interface layout, report sizes | Certain | Live descriptor from sysfs, parsed |
| Same HID layout as DK200 (BYK901) | Certain | Byte-for-byte comparison with the descriptor inside the OpenRGB #1804 capture |
| MCU is BYK901 / SH68F90A | High | DK200 + EWEADN TK100 issues, SMK docs; not opened physically |
| PID shared by different firmwares | Certain | AJAZZ AK510 capture (OpenRGB #762) shows another layout |
| Report 5 is the ISP channel | High | sinowealth-kb-tool specs for three 258a:002a boards; libratbag; not tested (by design) |
| Lighting write commands | Unknown | No source; capture required |
| Roles of reports 9–12 | Speculative | Sizes only; live reads pending the optional udev rule (§4) |
| Model is a Redragon K617 Fizz Rainbow (K617-R-B), fixed per-row colours | High | Owner identification + Redragon "-R" product line; the K617 RGB uses 258a:0049 |

## 8. Sources (retrieved 2026-10-29)

* OpenRGB, `Controllers/SinowealthController/` and `SinowealthControllerDetect.cpp`, master `aac7e5511439e020ddae88e78bd400c71b8d4a9c` — https://gitlab.com/CalcProgrammer1/OpenRGB
* OpenRGB issue #1804 "Dk200 Generic Keyboard" (BYK901, `dk200.plugin.pcapng`) — https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/1804
* OpenRGB issue #5006 "EWEADN TK100 with BYK901 (258A:002A)" — https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/5006
* OpenRGB issue #762 "AJAZZ AK510 Retro" (captures, 258a:002a with report 5/6 layout) — https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/762
* OpenRGB RFC #5951 "Possible remedy for controllers with protocol conflicts" — https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/5951
* sinowealth-kb-tool, `src/device_spec.rs`, `src/device_selector.rs`, `src/isp_device.rs`, master `242f7921357bad6df649efdd70c49dd059567ac7` — https://github.com/carlossless/sinowealth-kb-tool (read only; the tool was **not** run)
* SMK firmware docs, `docs/keyboards/eyooso-z11.md`, master `828d0386` — https://github.com/carlossless/smk
* libratbag `src/driver-sinowealth.c` (report IDs 4/5/6, command 0x75 = DFU) — https://github.com/libratbag/libratbag
* michauMiau/openrgb-gk850 (classic report 5/6 protocol, brick-risk notes) — https://github.com/michauMiau/openrgb-gk850
* chancellor1101/redragon-ks82b-rgb (0x0049, report 8) — https://github.com/chancellor1101/redragon-ks82b-rgb
* linux-hardware.org, USB 258a:002a — https://linux-hardware.org/?id=usb:258a-002a
* HAVIT KB487L report — https://github.com/brave/brave-browser/issues/57772
* Machenike K500 stuck-shift regression — https://github.com/zen-kernel/zen-kernel/issues/414
* SignalRGB public plugins (no 0x002A plugin), commit `95031635` — https://gitlab.com/signalrgb/signal-plugins
* Redragon K617 Fizz RGB user manual (Fn shortcuts, backlight modes) — https://gzhls.at/blob/ldb/6/7/e/0/fd543e7302a96b62efe1d68ad0c2f00ace1c.pdf
* fizz-rgb (Linux control for the K617 Fizz **RGB**, 258a:0049; MIT; PyPI `fizzctl`) — https://github.com/MrSchrodingers/fizz-rgb

---

## Resumo em português

* **Modelo identificado:** o teclado que aparece como `SINO WEALTH "Gaming KB"` (258a:002a) é um **Redragon K617 Fizz Rainbow (K617-R-B)**: 60%, 61 teclas, padrão US, corpo preto. Na versão **Rainbow** as cores dos LEDs são **fixas de fábrica por fileira** (vermelho, laranja/amarelo, verde, ciano/azul, roxo); pelas teclas Fn só se troca o modo (Fn + Alt direito), o brilho (Fn + M, 5 níveis) e a velocidade (Fn + vírgula, 5 níveis). **O Linux não muda cor.** Teste rápido: Fn + Espaço só faz o Espaço piscar nas cores no K617 **RGB**.
* **Se o seu for o K617 Fizz RGB (258a:0049):** use o [fizz-rgb](https://github.com/MrSchrodingers/fizz-rgb) (MIT, `fizzctl` no PyPI). Não mande os comandos dele ao 258a:002a.
* **Família:** MCU Sinowealth, quase certamente **BYK901 (SH68F90A)**. Os descritores HID das duas interfaces são **idênticos, byte a byte,** aos do teclado DK200 (issue #1804 do OpenRGB). O PID 258a:002a é reaproveitado por várias marcas e firmwares (o AJAZZ AK510 usa o mesmo PID com outro protocolo), então o PID sozinho não diz o protocolo.
* **Reports da interface 1:** feature 5 (5 bytes), 9 (**504**), 10 (41), 11 (126) e **12 (1920)**; entrada 1 (sistema), 2 (multimídia), 6 (NKRO) e 13 (mouse de macro).
* **Leitura:** GET_FEATURE é seguro e foi implementado (fd somente leitura).
* **Escrita:** **não há fonte confiável** com os comandos deste layout. O OpenRGB não suporta o 0x002A e desativou os teclados Sinowealth genéricos porque o código bricou teclados Redragon. **Nada foi escrito no teclado.** A página do teclado é só de pré-visualização e leitura, sem APLICAR de cor.
* **Perigo:** o report 5 da interface 1 também é o canal do bootloader (sinowealth-kb-tool: `05 75 00 00 00 00` entra no modo ISP). O módulo bloqueia qualquer escrita nele.
* **Privacidade:** a interface 1 também transporta as teclas no modo NKRO. Por isso a regra principal `udev/70-alienware-toolkit.rules` cobre só o mouse e o headset; a do teclado é a opcional `udev/71-sinowealth-keyboard-optional.rules`, instalada só com `./install.sh --keyboard-experimental` (com aviso). O painel nunca lê o fluxo de teclas.
* **O que falta para ter controle (modo, brilho, velocidade):** uma captura do software oficial da Redragon no Windows com USBPcap, uma ação por arquivo (seção 6), se houver software para a versão Rainbow. **Contribuições são bem-vindas.** Sem escrever nada, também dá para mapear os bytes no Linux: `python3 tools/sondar_teclado.py backup`, mudar a luz pelas teclas Fn e comparar as leituras.
* **Polling:** 1000 Hz (bInterval 1 ms), só leitura.
