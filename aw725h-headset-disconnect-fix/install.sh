#!/usr/bin/env bash
# Installs the AW725H guard as a systemd user service (no root needed).
#   ./install.sh              install and start the guard
#   ./install.sh --udev       also install the ModemManager rule (asks for sudo)
#   ./install.sh --uninstall  stop and remove the guard
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
    echo "Run as your normal user, without sudo (it asks for sudo only for --udev)."
    echo "Rode como seu usuário, sem sudo (ele pede sudo sozinho no --udev)."
    exit 1
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT=alienware-headset-guard.service
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now "$UNIT" 2>/dev/null || true
    rm -f "$UNIT_DIR/$UNIT"
    systemctl --user daemon-reload
    echo "Removed $UNIT."
    echo "If you installed the udev rule: sudo rm /etc/udev/rules.d/71-aw725h-modemmanager.rules"
    exit 0
fi

command -v pactl >/dev/null || { echo "pactl not found (install pulseaudio-utils)"; exit 1; }

mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/$UNIT" <<EOF
[Unit]
Description=Alienware AW725H dongle guard (stops the ~150 s reboot loop)
After=pipewire-pulse.service wireplumber.service
Wants=pipewire-pulse.service

[Service]
ExecStart=/usr/bin/python3 "$DIR/aw725h_guard.py"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT"
echo "Installed and started $UNIT (runs $DIR/aw725h_guard.py)."
echo "Log: journalctl --user -u ${UNIT%.service} -f"

if [ "${1:-}" = "--udev" ]; then
    sudo install -m 644 "$DIR/71-aw725h-modemmanager.rules" /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    echo "ModemManager rule installed (takes effect on the next dongle reconnect)."
fi
