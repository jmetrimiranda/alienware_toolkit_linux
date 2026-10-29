#!/usr/bin/env bash
# Instala as regras udev do Alienware Toolkit. Precisa de root (o ../install.sh chama com sudo;
# o botão "Dar permissão" do app chama com pkexec).
#   install-udev-rules.sh                          regra principal: mouse AW720M e dongle do headset AW725H
#   install-udev-rules.sh --keyboard-experimental  também a regra OPCIONAL do teclado 258a:002a (ver aviso)
#   install-udev-rules.sh --uninstall              remove as duas
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
    echo "Precisa de root / needs root: sudo $0 $*"
    exit 1
fi
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DESTINO=/etc/udev/rules.d
PRINCIPAL=70-alienware-toolkit.rules
TECLADO=71-sinowealth-keyboard-optional.rules

recarregar() {
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=hidraw --action=change
    udevadm settle
}

case "${1:-}" in
    --uninstall)
        rm -f "$DESTINO/$PRINCIPAL" "$DESTINO/$TECLADO" "$DESTINO/70-alienware-aw720m.rules"
        recarregar
        echo "Regras removidas / rules removed."
        exit 0 ;;
    ""|--keyboard-experimental) ;;
    *) echo "Opção desconhecida: $1"; exit 1 ;;
esac

rm -f "$DESTINO/70-alienware-aw720m.rules"   # regra antiga (só o mouse), de versões anteriores
install -m 644 "$DIR/$PRINCIPAL" "$DESTINO/"
echo "Instalada / installed: $DESTINO/$PRINCIPAL (mouse 413c:3028/3029, headset dongle 413c:ab2b)"
if [ "${1:-}" = "--keyboard-experimental" ]; then
    install -m 644 "$DIR/$TECLADO" "$DESTINO/"
    echo "Instalada / installed: $DESTINO/$TECLADO (teclado 258a:002a, interface 1)"
    echo "AVISO: a interface 1 também carrega as teclas digitadas (NKRO). Remova quando terminar de testar:"
    echo "WARNING: interface 1 also carries your keystrokes (NKRO). Remove it when you are done:"
    echo "  sudo rm $DESTINO/$TECLADO && sudo udevadm control --reload-rules"
elif [ -e "$DESTINO/$TECLADO" ]; then
    echo "Obs.: a regra opcional do teclado continua instalada ($DESTINO/$TECLADO)."
fi
recarregar
USUARIO="${SUDO_USER:-}"
[ -z "$USUARIO" ] && [ -n "${PKEXEC_UID:-}" ] && USUARIO="$(id -nu "$PKEXEC_UID")"
if [ -n "$USUARIO" ] && command -v getfacl >/dev/null; then
    for h in /dev/hidraw*; do
        getfacl -p "$h" 2>/dev/null | grep -q "^user:$USUARIO:" && echo "  $h: acesso para $USUARIO"
    done
fi
exit 0
