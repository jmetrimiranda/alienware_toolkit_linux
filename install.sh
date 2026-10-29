#!/usr/bin/env bash
# Alienware Toolkit for Linux: instalador (Ubuntu 24.04 / GNOME 46). Rode como seu usuário, SEM sudo:
# ele pede a senha sozinho só para copiar a regra udev.
#
#   ./install.sh                          .venv + regra udev (mouse e headset) + ícone, atalho e dock
#   ./install.sh --headset-fix            também instala o protetor do AW725H (aw725h-headset-disconnect-fix/)
#   ./install.sh --keyboard-experimental  também a regra udev OPCIONAL do teclado 258a:002a (lê as teclas!)
#   ./install.sh --no-desktop             sem ícone, atalho, dock e extensão do GNOME
#   ./install.sh --no-udev                sem regra udev (sem sudo)
#   ./install.sh --uninstall              desfaz tudo (atalho, extensão, regras udev, protetor e .venv)
set -euo pipefail

RAIZ="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APP="$RAIZ/alienware-command-center-linux"
FIX="$RAIZ/aw725h-headset-disconnect-fix"
VENV="$RAIZ/.venv"

msg() { printf '\033[36m==>\033[0m %s\n' "$*"; }
aviso() { printf '\033[33m!!\033[0m %s\n' "$*" >&2; }

if [ "$(id -u)" -eq 0 ]; then
    echo "Run as your normal user, without sudo (it asks for sudo only for the udev rule)."
    echo "Rode como seu usuário, sem sudo (ele pede a senha sozinho só para a regra udev)."
    exit 1
fi

COM_FIX=0; COM_TECLADO=0; COM_DESKTOP=1; COM_UDEV=1; DESINSTALAR=0
for arg in "$@"; do
    case "$arg" in
        --headset-fix) COM_FIX=1 ;;
        --keyboard-experimental) COM_TECLADO=1 ;;
        --no-desktop) COM_DESKTOP=0 ;;
        --no-udev) COM_UDEV=0 ;;
        --uninstall) DESINSTALAR=1 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) aviso "Opção desconhecida: $arg"; sed -n '2,11p' "$0"; exit 1 ;;
    esac
done

if [ "$DESINSTALAR" -eq 1 ]; then
    msg "Removendo ícone, atalho, favorito da dock e extensão"
    "$RAIZ/desktop/install-desktop.sh" --uninstall || true
    if systemctl --user cat alienware-headset-guard.service >/dev/null 2>&1; then
        msg "Removendo o protetor do headset (alienware-headset-guard.service)"
        "$FIX/install.sh" --uninstall || true
    fi
    msg "Removendo as regras udev (pede a senha)"
    sudo bash "$RAIZ/udev/install-udev-rules.sh" --uninstall || true
    if [ -e /etc/udev/rules.d/71-aw725h-modemmanager.rules ]; then
        sudo rm -f /etc/udev/rules.d/71-aw725h-modemmanager.rules && sudo udevadm control --reload-rules || true
    fi
    msg "Apagando $VENV"
    rm -rf "$VENV"
    msg "Pronto. As suas configurações ficam em ~/.config/alienware-toolkit (apague se quiser)."
    exit 0
fi

# ---------- 1. dependências do sistema (GTK 4, libadwaita, WebKit 6.0 para o 3D) ----------
msg "Conferindo GTK 4, libadwaita e WebKit 6.0"
if ! python3 - <<'PY' 2>/dev/null
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: F401
PY
then
    aviso "Faltam pacotes do sistema. Instale com:"
    echo "    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-rsvg-2.0 gir1.2-webkit-6.0"
    exit 1
fi
if ! python3 -c 'import gi; gi.require_version("WebKit", "6.0"); from gi.repository import WebKit' 2>/dev/null; then
    aviso "WebKit 6.0 não encontrado: o app abre com as ilustrações SVG no lugar do 3D."
    aviso "Para o 3D: sudo apt install gir1.2-webkit-6.0"
fi
command -v pactl >/dev/null || aviso "pactl não encontrado (pulseaudio-utils): o protetor do headset precisa dele."

# ---------- 2. .venv com os pacotes do sistema ----------
msg "Criando $VENV (--system-site-packages, usa o PyGObject do Ubuntu)"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/python" -m pip install --quiet -r "$RAIZ/requirements.txt"
chmod +x "$APP/run.sh" "$RAIZ"/tools/*.sh "$RAIZ"/desktop/install-desktop.sh "$FIX"/*.sh "$RAIZ"/udev/*.sh

# ---------- 3. regra udev (a única parte com sudo) ----------
if [ "$COM_UDEV" -eq 1 ]; then
    if [ "$COM_TECLADO" -eq 1 ]; then
        aviso "Regra OPCIONAL do teclado 258a:002a: a interface 1 também carrega as teclas digitadas (NKRO)."
        aviso "Com ela, qualquer programa da sua sessão poderia ler o que você digita. Use só para testar."
        read -rp "Instalar mesmo assim? Digite 'sim' / type 'yes': " resposta
        case "$resposta" in sim|yes) ;; *) COM_TECLADO=0; msg "Regra do teclado pulada." ;; esac
    fi
    msg "Instalando a regra udev (pede a senha)"
    if [ "$COM_TECLADO" -eq 1 ]; then
        sudo bash "$RAIZ/udev/install-udev-rules.sh" --keyboard-experimental
    else
        sudo bash "$RAIZ/udev/install-udev-rules.sh"
    fi
fi

# ---------- 4. protetor do headset AW725H ----------
if [ "$COM_FIX" -eq 1 ]; then
    msg "Instalando o protetor do AW725H (serviço do usuário + regra do ModemManager)"
    "$FIX/install.sh" --udev
fi

# ---------- 5. ícone, atalho, dock e extensão do GNOME ----------
if [ "$COM_DESKTOP" -eq 1 ]; then
    msg "Instalando ícone, atalho, favorito da dock e extensão de hover"
    "$RAIZ/desktop/install-desktop.sh" "$APP"
fi

echo
msg "Pronto! Abra pelo menu (Alienware Toolkit) ou rode: $APP/run.sh"
[ "$COM_DESKTOP" -eq 1 ] && msg "No Wayland, saia e entre na sessão uma vez para a extensão da dock carregar."
exit 0
