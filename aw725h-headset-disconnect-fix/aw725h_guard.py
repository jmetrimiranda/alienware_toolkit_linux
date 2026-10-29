#!/usr/bin/env python3
"""Alienware AW725H dongle guard for Linux (PipeWire).

Problem: with dongle firmware 1.00, the AW725H USB dongle (413c:ab2b) reboots itself
~140-150 s after an audio stream starts. You hear the sound cut, the device disappears
for 3-5 s and apps jump to another output.

Finding: the timer counts from the moment the PCM stream (re)starts, not from the USB
connection. If the stream is fully closed and reopened before the limit, the counter
starts over and the dongle never reboots.

What this guard does, every `interval_s` seconds of continuous playback:
  1. creates a temporary null sink and moves the headset's streams to it,
  2. suspends the headset sink (the ALSA PCM is really closed, like a reconnect),
  3. waits `pause_s`, resumes the sink and moves the streams back,
  4. removes the null sink.
Result: a ~0.5 s gap instead of a 3-5 s disconnect.

Do NOT shorten this to a plain `pactl suspend-sink 1/0` while a stream is playing: that
only stops/starts the PCM for ~16 ms, and the dongle may then play on ONE side only.

Config (optional): config.json next to this file. State: ~/.local/state/aw725h-guard/status.json
"""

import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "config.json")
STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                         "aw725h-guard")
STATUS_FILE = os.path.join(STATE_DIR, "status.json")

DEFAULTS = {
    "interval_s": 110,         # reopen the stream after this many seconds of playback (< ~140 s)
    "pause_s": 0.3,            # how long the PCM stays closed
    "usb_id": "413c:ab2b",     # AW725H dongle
    "sink_match": "AW725H",    # piece of the PipeWire sink name
}
PAUSE_SINK = "aw725h_guard_pause"


def log(text):
    # stdout goes to the journal: journalctl --user -u alienware-headset-guard
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}", flush=True)


def load_config():
    config = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            config.update(json.load(f))
    return config


def pactl(*args):
    return subprocess.run(["pactl", *args], capture_output=True, text=True).stdout


def find_sink(sink_match):
    """Return (index, name) of the headset sink, or None."""
    for line in pactl("list", "sinks", "short").splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and sink_match in parts[1] and PAUSE_SINK not in parts[1]:
            return parts[0], parts[1]
    return None


def find_pcm_status(usb_id):
    """Path of the playback PCM status file of the dongle (the card number changes on reconnect)."""
    for card in sorted(os.listdir("/proc/asound")):
        usbid_file = f"/proc/asound/{card}/usbid"
        if card.startswith("card") and os.path.exists(usbid_file):
            with open(usbid_file) as f:
                if f.read().strip() == usb_id:
                    return f"/proc/asound/{card}/pcm0p/sub0/status"
    return None


def seconds_playing(pcm_status):
    """How long the PCM has been RUNNING (0 if stopped or closed)."""
    try:
        with open(pcm_status) as f:
            text = f.read()
    except OSError:
        return 0
    if "state: RUNNING" not in text:
        return 0
    for line in text.splitlines():
        if line.startswith("trigger_time:"):
            started = float(line.split()[1])
            return time.clock_gettime(time.CLOCK_MONOTONIC) - started
    return 0


def reopen_stream(sink_index, sink_name, pause_s, pause_sink=PAUSE_SINK):
    """Fully close and reopen the headset PCM without losing the streams."""
    streams = []
    for line in pactl("list", "sink-inputs", "short").splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and parts[1] == sink_index:
            streams.append(parts[0])
    module = pactl("load-module", "module-null-sink", f"sink_name={pause_sink}",
                   "sink_properties=device.description=AW725H-guard-pause").strip()
    try:
        for stream in streams:
            pactl("move-sink-input", stream, pause_sink)
        pactl("suspend-sink", sink_name, "1")
        time.sleep(pause_s)
        pactl("suspend-sink", sink_name, "0")
        for stream in streams:
            pactl("move-sink-input", stream, sink_name)
    finally:
        if module:
            pactl("unload-module", module)
    return len(streams)


def count_resets(since):
    """Dongle reboots seen in the kernel log (the MediaTek bootloader shows up as 0e8d:0003).

    Needs permission to read the kernel journal (group adm or systemd-journal); None otherwise.
    """
    result = subprocess.run(["journalctl", "-k", "--since", since, "--no-pager", "-q"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.count("idVendor=0e8d, idProduct=0003")


def save_status(status):
    status["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f)


def main():
    config = load_config()
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    status = {"active": True, "interventions": 0, "last_intervention": None,
              "resets_detected": 0, "mode": "waiting for audio", "since": started}
    log(f"Guard started (interval {config['interval_s']} s, pause {config['pause_s']} s)")
    last_check = 0
    while True:
        sink = find_sink(config["sink_match"])
        pcm = find_pcm_status(config["usb_id"])
        if sink is None or pcm is None:
            status["mode"] = "headset not connected"
        else:
            playing = seconds_playing(pcm)
            status["mode"] = f"playing for {playing:.0f} s" if playing else "no audio"
            if playing >= config["interval_s"]:
                moved = reopen_stream(sink[0], sink[1], config["pause_s"])
                status["interventions"] += 1
                status["last_intervention"] = time.strftime("%H:%M:%S")
                log(f"Stream reopened after {playing:.0f} s ({moved} stream(s) moved)")
        if time.time() - last_check > 30:  # the kernel log is checked every 30 s only
            resets = count_resets(started)
            if resets and resets != status["resets_detected"]:
                log(f"Dongle reboots since start: {resets}")
            status["resets_detected"] = resets
            last_check = time.time()
        save_status(status)
        time.sleep(1)


def one_shot(args):
    """Manual helpers, also used by the control panel:
       --reopen [pause_s]  reopen the headset stream now (fixes audio stuck on ONE side)
       --channel-test      say "Front Left" / "Front Right" on each side of the headset
    """
    if args[0] not in ("--reopen", "--channel-test"):
        sys.exit(one_shot.__doc__)
    config = load_config()
    sink = find_sink(config["sink_match"])
    if sink is None:
        sys.exit("Headset not connected")
    if args[0] == "--reopen":
        pause = float(args[1]) if len(args) > 1 else 1.0
        moved = reopen_stream(sink[0], sink[1], pause, pause_sink=PAUSE_SINK + "_manual")
        print(f"Stream reopened ({moved} stream(s) moved, pause {pause} s)")
    elif args[0] == "--channel-test":
        # The WAVs are mono: --channel-map pins each one to a single side (otherwise both sides play it)
        for side, channel in (("Left", "FL"), ("Right", "FR")):
            subprocess.run(["pw-play", "--target", sink[1], "--channel-map", channel,
                            f"/usr/share/sounds/alsa/Front_{side}.wav"])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        one_shot(sys.argv[1:])
        sys.exit(0)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # systemctl stop -> clean exit
    try:
        main()
    finally:
        save_status({"active": False, "interventions": 0, "last_intervention": None,
                     "resets_detected": 0, "mode": "stopped", "since": None})
        log("Guard stopped")
