# Alienware AW725H headset on Linux

Status of every AWCC feature of the **Alienware Tri-Mode Wireless Gaming Headset AW725H** on Linux
(Ubuntu 24.04, PipeWire 1.0.5, WirePlumber 0.4.17), what this toolkit implements, and how.
Researched and tested on 2026-10-29 with the USB-C dongle `413c:ab2b` (dongle firmware 1.00).
Portuguese summary at the end.

## TL;DR

| Feature (AWCC on Windows) | Linux status | How |
|---|---|---|
| Audio out / mic | **Works** (USB Audio Class) | `snd-usb-audio`, PipeWire sink + source |
| Dongle reboots every ~150 s of audio (fw 1.00) | **Worked around** | `alienware-headset-guard.service` from [`aw725h-headset-disconnect-fix/`](../aw725h-headset-disconnect-fix/); real fix = firmware 1.8.0/1.1.0 on Windows |
| Sound on one side only after the stream reopens (fw 1.00) | **One-click workaround** | `aw725h_guard.py --reopen 1.0` (button *REPARAR SOM AGORA* in the app); see §5 |
| Hardware volume / mic gain / mute | **Works** | ALSA mixer of the dongle (`amixer -c Dongle`) → `headset_aw725h.py`, tab **MIC** |
| Equalizer + presets | **Works (software)** | PipeWire filter-chain virtual sink "AW725H EQ" → `equalizador.py`, tab **EQ** |
| Hear your own voice (sidetone) | **Works (software)** | `pw-loopback` mic → headset, ~40–80 ms latency, tab **MIC** |
| Media buttons (volume wheel, play, mute key) | **Works** | Standard HID consumer report 2 (the kernel already maps it) |
| RGB lighting (Alien Head logo, AlienFX) | **Preview only** | Protocol unknown → needs a USBPcap capture on Windows ([plan](usbpcap-capture-plan-pt.md)) |
| Battery level | **Works (read-only)** | **One value for the whole headset** (single internal battery, no per-side battery). The dongle pushes report 8 `c0 09 03 00 02 <value> <xor>` by itself when the value changes (~70 s in use, ~18 s charging); decoded and shown in tab **BATERIA** |
| Other notice (subtype 01) | **Unknown** | Two-state event `0xdd`/`0xcc`, shown raw |
| Charging state | **Inferred** | No charger flag was seen; the reader marks "charging" when the level goes up |
| Auto power-off | n/a | Fixed in the headset (30 min after losing the dongle); AWCC has no setting for the AW725H |
| Dolby Atmos for Headphones | **No** | Windows-only (Dolby Access app) |
| Firmware update / factory reset | **No** (on purpose) | Windows only; a failed update can brick the dongle |

## 1. Hardware facts

| Item | Value |
|---|---|
| USB | `413c:ab2b` "Dell Inc AW725H Dongle", full speed, `bcdDevice 1.00` |
| Interface 0 | Audio Control (headset terminals) |
| Interface 1 | Audio Streaming OUT, 48 kHz, S16_LE, stereo (EP `0x01`, adaptive) |
| Interface 2 | Audio Streaming IN, mono, 16/48 kHz (EP `0x81`) |
| Interface 3 | HID, **IN endpoint only** (`0x83`, 64 bytes), report descriptor 80 bytes |
| ALSA card | `Dongle` (number changes after each dongle reboot, the id does not) |
| Mixer | `PCM Playback Volume` 0–74 (−74…0 dB, 1 dB/step), `PCM Playback Switch`, `Headset Capture Volume` 0–30 (−30…0 dB), `Headset Capture Switch` |
| Windows endpoints | "AW725H Game" / "AW725H Chat" are virtual (driver/APO); the dongle exposes **one** playback and **one** capture stream |

PipeWire uses the hardware mixer as the sink volume, so `PCM Playback Volume` and the GNOME
volume slider move together (e.g. 60/74 = −14 dB ⇔ GNOME ~45%).

### HID report descriptor (interface 3), decoded

```
06 13 ff     Usage Page (Vendor 0xFF13)
09 01 a1 01  Usage 1, Collection (Application)
15 00 26 ff 00   Logical 0..255
85 06 09 00 75 08 95 3d 91 02   Report 6: OUTPUT, 61 bytes   (host → dongle, commands)
85 07 09 00 75 08 95 3d 81 02   Report 7: INPUT,  61 bytes   (dongle → host, replies)
85 08 09 00 75 08 95 07 81 02   Report 8: INPUT,   7 bytes   (dongle → host, notifications)
c0
05 0c 09 01 a1 01   Consumer Control
85 02 15 00 25 01   Report 2, 1-bit fields:
09 e9 09 ea 09 e2 09 cd 09 b5 09 b6   Vol+, Vol−, Mute, Play/Pause, Next, Previous
75 01 95 06 81 02   6 bits
09 00 95 02 81 02   2 bits padding
c0
```

On `hidraw` each report starts with its ID byte (report 7 = 62 bytes, report 8 = 8 bytes).
Since the interface has no OUT endpoint, report 6 can only be sent as a `SET_REPORT` control
transfer (`bmRequestType 0x21`, `wValue 0x0206`, `wIndex 3`). **This toolkit never sends it.**

## 2. What AWCC offers for the AW725H (research)

Sources: AW725H User's Guide (Dell, PDF), Dell product pages (US/UK), Dell KB 000208666,
AWCC 6.x User's Guide, Alienware Pro Wireless Headset guide (for comparison), HeadsetControl,
alienfx-tools and OpenRGB device lists.

- **AWCC for the AW725H is thin.** The user guide lists only: connection type (USB cable or
  wireless receiver), **battery level and charging status**, firmware version/upgrade and
  factory reset. AWCC 6.4+ is required for **AlienFX lighting** and the "Launch Dolby Atmos" link
  (Dell product page, *Compatibility*). AWCC does not work over Bluetooth.
- **RGB lighting exists**: one zone, the **Alien Head logo on the ear cups** ("AlienFX syncs with
  AWCC to provide a customizable array of RGB lighting"). Battery life is 58 h (2.4 GHz) with RGB
  off vs. 35 h with RGB on. The power LED is a status LED (green/amber/blue), not RGB.
  RGB does not work in 3.5 mm inline mode.
- **EQ / sidetone / mic monitoring / auto-off settings**: *not documented for the AW725H*. Those
  settings (Sound tab: volume, Hybrid ANC, Dolby link; Microphone tab: volume, **sidetone**, mic
  noise cancellation, mic test; Battery tab: battery saver, **sleep mode**) belong to the
  **Alienware Pro Wireless** headset. Some user reports mention changing EQ in AWCC with the
  AW725H, which most likely is the generic Windows-side audio/Dolby processing.
- **Auto power-off**: fixed, 30 min after the dongle connection is lost (user guide).
- **Battery**: 750 mAh Li-Po, < 2.5 h full charge, < 20% → power LED blinks amber and the logo
  blinks fast.
- **On-headset controls** handled by the headset itself: volume wheel, Game/Chat balance button
  (it balances the Windows "Game" and "Chat" endpoints; with the single stream seen on Linux it
  probably has no useful effect), mic mute button (red LED; mic also mutes when retracted).
- **No public HID protocol** for AW725H/AW720H/AW920H/Pro Wireless: not in HeadsetControl
  (no Alienware device), not in alienfx-tools (lights for laptops/desktops, mice APIv7,
  keyboards APIv8, monitors APIv6; no headsets), not in OpenRGB (Alienware keyboards only).
  The AW720M mouse protocol (APIv7, 64-byte reports without report ID) does not match this
  descriptor (report IDs 6/7/8, 61 bytes), so it was **not** tried.

## 3. Passive HID listening

Method: [`tools/escuta_passiva.py`](../tools/escuta_passiva.py) opened the interface-3 hidraw **read-only** (`O_RDONLY`;
nothing can be written to the dongle) for 26 minutes (09:01–09:27, 2026-10-29), logging every
report with a timestamp, plus a context snapshot every 15 s (PCM state, mixer values) to
correlate. Raw data: [`data/aw725h-hid-listen-20261029-090105.log`](data/aw725h-hid-listen-20261029-090105.log) (the context snapshots stayed in the development lab).

**Result: 14 reports in 26 min, all report 8, none of report 7 or 2** (no media key was pressed).
Every report 8 had the same frame shape, the one the AW720M mouse uses for its unsolicited
power notice (`c0 0a …`, Dell "APIv7" family):

```
08 | c0 | 09 | 03 | 00 | ST | VV | CK
id  notice event len  —   subtype value checksum
```

- **Checksum:** `CK` = XOR of all previous bytes *including the report ID 08*; the XOR of the
  whole report is 0. Valid in **14 of 14** reports. `headset_aw725h.checksum_ok()` checks it.
- **Subtype 02 = battery %** (confirmed by charging, see below): 27, 26, 25 … 18, one step per notice.
  The dongle samples it on a ~70.1 s grid and only sends a notice when the value changes:
  gaps of 140.2 s (most of the run), 210.3 s twice, and 70.2 s at the end (the drop speeds up
  near 20%, as a voltage-based gauge on a Li-Po near empty would). This is faster than the
  nominal drain (~3%/h for 35 h with RGB on), so the headset's number is an estimate (most
  likely from the cell voltage). The headset went under 20% at 09:23 (manual: power LED blinks
  amber).
- **Subtype 01 = two-state event, unknown**: only `0xdd` followed by `0xcc`, as pairs 29 s and
  13.5 s apart, twice (09:04:48/09:05:18 and 09:25:02/09:25:16). Too few distinct values to be a
  signal-strength reading; candidates are the mic-mute button, the mic boom or a radio/link
  state. Shown raw in the BATERIA tab.
- Nothing correlated with the context (PCM always RUNNING, capture closed, mixer 60/74
  constant) nor with the guard interventions (every ~110 s).
- Curiosity: 140 s (2 × 70.1 s) is also the time after which firmware 1.00 reboots the dongle
  when audio plays continuously; the battery-sampling task may be involved. Hypothesis only.

| Time | Bytes | Decoded |
|---|---|---|
| 09:04:35 | `08 c0 09 03 00 02 1b db` | level 27 |
| 09:04:48 | `08 c0 09 03 00 01 dd 1e` | subtype 01 = 0xdd |
| 09:05:18 | `08 c0 09 03 00 01 cc 0f` | subtype 01 = 0xcc |
| 09:06:55 → 09:26:47 | `… 02 1a da` … `… 02 12 d2` | level 26 → 18 (8 notices) |
| 09:25:02 / 09:25:16 | `… 01 dd 1e` / `… 01 cc 0f` | subtype 01 pair again |

Full table: [`data/aw725h-hid-listen-analysis.md`](data/aw725h-hid-listen-analysis.md) (generated by [`tools/analisar_escuta.py`](../tools/analisar_escuta.py)).

**Charging run (09:29–09:35, [`data/aw725h-hid-listen-20261029-092936.log`](data/aw725h-hid-listen-20261029-092936.log), 16 reports):** right after the
26-min run the level started to **rise**: 21 at 09:29:18 (seen live by the app's reader), then
23 → 36 in steps of exactly **18.0 s**, then 37 and 38 every 50 s. That is what a charging
headset does (the cable was presumably plugged in around 09:28; this job did not see it), so
subtype 02 is the battery level. No separate "charging" notice appeared; only the faster
sampling and the rising value tell it apart. Table: [`data/aw725h-hid-listen-charging-analysis.md`](data/aw725h-hid-listen-charging-analysis.md).

**Not found by listening:** an explicit charging flag, a battery value on demand (AWCC most
likely asks for it with a report-6 command answered on report 7), lighting state. Those need
the Windows capture.

## 4. Implementation

All files below live in [`alienware-command-center-linux/`](../alienware-command-center-linux/) unless noted.

| File | What it does |
|---|---|
| `headset_aw725h.py` | `LeitorPassivo` (thread, read-only hidraw, auto-reopen after a dongle reboot, parser `interpretar()` with XOR check; battery in `estado['bateria']` / `estado['carregando']`, last value saved to `~/.local/state/alienware-toolkit/aw725h.json`); mixer `ler_mixer()` / `definir()` via `amixer -c Dongle`; `MonitorMicrofone` (pw-loopback). CLI: `python3 headset_aw725h.py mixer` or `escutar 60`. |
| `equalizador.py` | Presets, `gerar_conf()` (filter-chain fragment or full config), `ligar()` / `desligar()` through the user's `filter-chain.service`, `aplicar_ao_vivo()` (pw-cli set-param, no audio gap), `estado()`, `resposta_em_frequencia()` (RBJ biquads, for the plot). |
| `ui/abas_headset_extras.py` | Tabs **MIC**, **EQ**, **LUZ** (lighting) and **BATERIA** of the headset page, project style, pt-BR tooltips on every control. |
| `ui/pagina_headset.py` | The headset page: tabs Estado (with *Som de um lado só?*), Estabilidade, Proteção, Áudio + the four tabs above; bottom bar **↻ ATUALIZAR** (re-reads connection, reboots, guard and audio; sends nothing to the headset) and **CANCELAR / APLICAR** when the EQ or mic tab has something pending. |
| [`tools/escuta_passiva.py`](../tools/escuta_passiva.py), [`tools/analisar_escuta.py`](../tools/analisar_escuta.py) | Passive listening of the dongle's HID channel (read-only) and log → Markdown table. |
| [`aw725h-headset-disconnect-fix/`](../aw725h-headset-disconnect-fix/) | The guard (`aw725h_guard.py`, systemd user service) and its one-shot helpers `--reopen` and `--channel-test`. |

The HID reader needs the udev rule [`udev/70-alienware-toolkit.rules`](../udev/70-alienware-toolkit.rules)
(`uaccess` for `413c:ab2b`), installed by `./install.sh`; mixer, EQ and mic monitor work without it.

### 4.1 Equalizer (software, PipeWire filter-chain)

```
apps ──> "AW725H EQ" (sink, node.name alienware_eq)
            pre-gain → 31 Hz low-shelf → 62…8k peaking (Q 1.41) → 16 kHz high-shelf
            ▼
         alienware_eq.saida (playback stream = sink-input of the AW725H sink, node.passive)
            ▼
         AW725H Dongle Analog Stereo
```

- 10 octave bands (31 Hz–16 kHz), ±12 dB, plus an automatic **pre-gain** = −(largest boost)
  so boosts never clip (`bq_highshelf` at 0 Hz = flat gain, the AutoEq idiom).
- Presets: **Plano** (flat), **Graves+** (+6 dB at 31 Hz sloping down), **Passos FPS** (−5 dB
  lows, +3…+5 dB at 2–4 kHz for footsteps), **Voz** (cuts lows, +3…+4 dB at 1–2 kHz),
  **Personalizado** (user's 10 bands, saved in `~/.config/alienware-toolkit/eq.json`).
- **Turning it on (app):** writes `~/.config/pipewire/filter-chain.conf.d/aw725h-eq.conf` and
  restarts only the user's `filter-chain.service` (ships with Ubuntu 24.04 and is already enabled;
  the main PipeWire and the guard keep running), then optionally makes "AW725H EQ" the default
  output. **Off:** deletes the fragment, restarts `filter-chain.service`, sets the AW725H back
  as default. Preset changes while it is on are applied live with
  `pw-cli set-param <id> Props '{ params = [ "b1:Gain" 6.0 … ] }'`.
- Alternative: `equalizador.gerar_conf(ganhos, completo=True)` produces a full config for a standalone `pipewire -c <file>` instance.
- **Node name caveat:** the guard finds the headset sink with `"AW725H" in node.name`, so the EQ
  sink is named `alienware_eq` (only its description says "AW725H EQ").

**Tested (temporary instance from `~/lab`, never the default sink):** the sink appeared, its
output linked to the AW725H and showed up as a sink-input of it; silence (a WAV of zeros) was
played through it; the live preset change worked (`pre:Gain` −6 → −5 dB read back from
`pw-dump`); at the next guard intervention the guard log said "3 stream(s) moved" (Chrome,
speech-dispatcher **and the EQ output**), the EQ output was seen on `aw725h_guard_pause` and was
back on the AW725H afterwards, playback through the EQ kept running, and the default sink never
changed.

### 4.2 Microphone

- Hardware gain/mute and headphone volume/mute: the four ALSA controls, applied immediately
  (250 ms debounce while dragging), same as the existing *Áudio* tab does with `wpctl`.
- No hardware sidetone control is exposed by the dongle. "Ouvir a própria voz" starts
  `pw-loopback -C <AW725H source> -P <AW725H sink>` (mono → both ears) with its own volume
  (`wpctl set-volume` on `output.aw725h_monitor_mic`). Its output is a sink-input of the AW725H,
  so the guard moves it like any other stream. Tested with virtual nodes: links, volume and clean
  shutdown OK; the process is killed at app exit (`atexit`).
- The headset's own mute button works inside the headset and is not reflected in ALSA.

### 4.3 Lighting

Tab **LUZ** = preview only, with the warning "REQUER CAPTURA NO WINDOWS". The headset page shows
the 3D viewer (`ui/visualizador3d.py`, black "Dark Side of the Moon" body by default, changeable in
Settings) and the tab drives it through `set_light('logo', hex)`, `set_effect(name, c1, c2, speed)`
and `set_brightness()`; without WebKit/WebGL the page falls back to the static SVG and the tab shows
its own animated ear-cup drawing. Effects: fixo, respirar, transição, espectro, pulsar, arco-íris;
brightness, speed, "luz acesa" (Go Dark). Clicking an ear-cup logo in the 3D view opens this tab.
Nothing is sent to the headset.
Capture plan: [usbpcap-capture-plan-pt.md](usbpcap-capture-plan-pt.md).

### 4.4 Battery: one value for the whole headset

The AW725H has **one internal battery** (750 mAh Li-Po) that powers both ear cups, so there is
**no per-side battery**: the app shows a single percentage. Tab **BATERIA** shows the level from the
last subtype-02 notice (report 8 `c0 09 … 02 <value> <xor>`, read passively), with the time it
arrived and "subindo (carregando)" / "descendo (em uso)" from the last change. The last value is
saved to `~/.local/state/alienware-toolkit/aw725h.json`, so the next app start shows the last
known value. Until the first notice arrives (the dongle only reports when the value changes) the
app says **"não informado pelo dongle"** ("not reported by the dongle"); asking for it on demand
would need the AWCC command (Windows capture). The tab also shows the read-only HID reader state
(device, permission, report counts, last report 7/8, subtype 01, last button) and the manual's
battery facts.

## 5. Sound on one side only

**Symptom:** after the audio stream is reopened (a guard intervention, a short pause, an app that
closes and reopens its output) the headset sometimes keeps playing on **one ear only**.

**Cause:** dongle firmware 1.00. Linux sends both channels with the same level (the sink is plain
stereo, nothing is panned); the dongle itself sometimes comes back from a stream restart with one
channel dead. It happened reliably with a 16 ms pause (`pactl suspend-sink 1/0` while playing),
which is why the guard closes the PCM for real, and apparently once in a while also after a normal
guard intervention.

**Fix (one click, nothing is sent to the HID channel):** reopen the stream with a longer pause, as
in a reconnect:

```bash
python3 aw725h-headset-disconnect-fix/aw725h_guard.py --channel-test   # says "Front Left" / "Front Right", one per ear
python3 aw725h-headset-disconnect-fix/aw725h_guard.py --reopen 1.0     # closes the PCM for 1 s and brings the streams back
```

In the app: headset page → tab **Estado** → section **"Som de um lado só?"** with the buttons
**TESTAR CANAIS (E/D)** and **REPARAR SOM AGORA** (they run the two commands above). If it does not
come back, click again, or switch the headset off and on. The definitive fix is the firmware update
(headset 1.8.0 + dongle 1.1.0, on Windows).

## 6. Tests done

- `py_compile` of all modules; mixer read; parser on synthetic reports.
- Temporary EQ instance + guard intervention (above); mic monitor with virtual source/sink.
- All four tabs rendered inside the real app on `gtk4-broadwayd` (Broadway backend),
  screenshots reviewed (see [`docs/media/`](media/)). In capture mode the lighting
  preview is a still frame (an animating widget makes the window snapshot empty on broadway).

## 7. Next steps

1. USBPcap capture on Windows (lighting, battery, button/status events) → implement only the
   captured commands ([plan](usbpcap-capture-plan-pt.md)).
2. Firmware headset 1.8.0 + dongle 1.1.0 (Windows), then re-test without the guard.
3. Publish the battery to UPower (like OpenRazer does) and add a low-battery notification (< 20%).
4. Decode subtype 01 (`0xdd`/`0xcc`): press the mic-mute button and retract the mic while
   `python3 alienware-command-center-linux/headset_aw725h.py escutar 300` runs and note which action produces it.

---

## Resumo em português

- **O que funciona no Linux:** áudio e microfone; volume e ganho de hardware e mudo pelo mixer
  ALSA do dongle (aba **MIC**); **equalizador por software** no PipeWire com presets Plano,
  Graves+, Passos FPS, Voz e Personalizado de 10 bandas (aba **EQ**); retorno da própria voz por
  software (pw-loopback); botões de mídia do headset (report 2 padrão); **bateria em %** lida dos
  avisos que o dongle manda sozinho (aba **BATERIA**, só leitura).
- **Bateria única:** o AW725H tem **uma bateria interna para os dois lados**; não existe bateria por
  lado, então o painel mostra um valor só. Até chegar o primeiro aviso, aparece "não informado pelo
  dongle".
- **Som de um lado só:** com o firmware 1.00, o dongle às vezes volta tocando de um lado só depois que
  o stream reabre. O Linux manda os dois canais iguais; o problema é do dongle. Na aba **Estado**,
  seção "Som de um lado só?": **TESTAR CANAIS (E/D)** (`aw725h_guard.py --channel-test`) e **REPARAR
  SOM AGORA** (`aw725h_guard.py --reopen 1.0`, reabre o stream com pausa de 1 s, como numa
  reconexão). Se não resolver, clique de novo ou desligue e ligue o headset.
- **O que o AWCC tem para o AW725H:** só conexão, bateria, firmware/reset e **iluminação RGB do
  logo Alien Head nas conchas** (AlienFX, AWCC ≥ 6.4). EQ, sidetone e "sleep mode" do AWCC são do
  headset Alienware Pro Wireless, não do AW725H. Desligamento automático é fixo (30 min sem o
  dongle). Dolby Atmos é só do Windows.
- **Protocolo HID:** nenhum projeto público documenta headsets Alienware. O canal de fabricante
  (usage page 0xFF13: report 6 saída, 7 e 8 entrada) foi lido **só em modo leitura** por 26 min.
  Vieram 14 avisos no report 8, formato `08 c0 09 03 00 <subtipo> <valor> <xor>` (o último byte é
  o XOR de todos os anteriores, válido em 14 de 14). Subtipo 02 = **bateria em %**: caiu de 27 para
  18 em uso (o dongle confere a cada ~70 s e só avisa quando muda) e, numa escuta extra de 6 min,
  **subiu** de 21 para 38 (um ponto a cada 18 s), o que bate com o headset carregando. A aba
  BATERIA mostra o valor e deduz "carregando" quando ele sobe. Subtipo 01 = evento de dois estados
  (0xdd → 0xcc), ainda sem significado. Nada foi enviado ao dongle.
- **Luz:** aba **LUZ** só pré-visualiza (no 3D, se houver) com o aviso "requer captura no
  Windows"; o plano de captura com USBPcap está em [`usbpcap-capture-plan-pt.md`](usbpcap-capture-plan-pt.md).
- **EQ × protetor:** testado com uma instância temporária: a saída do EQ é um sink-input do AW725H,
  o protetor moveu "3 streams" (incluindo o EQ) e devolveu; o som pelo EQ continuou e a saída
  padrão não mudou. O nó do EQ se chama `alienware_eq` de propósito (o protetor procura
  "AW725H" no nome do sink).
- **Onde fica:** módulos `headset_aw725h.py` e `equalizador.py` e as abas em `ui/abas_headset_extras.py`, todos em `alienware-command-center-linux/`, já integrados em `ui/pagina_headset.py`. O protetor fica em `aw725h-headset-disconnect-fix/`.
