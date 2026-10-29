#!/usr/bin/env bash
# Do I have the AW725H reboot-loop problem? / Eu tenho o problema do AW725H?
#   ./check.sh [minutes]   (default 30; keep some audio playing on the headset)
MIN=${1:-30}
SIG='idVendor=0e8d, idProduct=0003'   # MediaTek bootloader = the dongle rebooting

dev=$(grep -lx 'ab2b' /sys/bus/usb/devices/*/idProduct 2>/dev/null | xargs -r -n1 dirname |
      while read -r d; do [ "$(cat "$d/idVendor")" = 413c ] && echo "$d"; done | head -1)
if [ -z "$dev" ]; then
    echo "AW725H dongle (413c:ab2b) not found / dongle não encontrado."
    exit 1
fi
fw=$(cat "$dev/bcdDevice")
echo "Dongle:   413c:ab2b on port $(basename "$dev"), $(cat "$dev/speed") Mb/s, firmware $((10#${fw:0:2})).${fw:2:2}"

playing="no"
for card in /proc/asound/card*; do
    [ "$(cat "$card/usbid" 2>/dev/null)" = 413c:ab2b ] && grep -q RUNNING "$card/pcm0p/sub0/status" 2>/dev/null && playing="yes"
done
echo "Audio:    playing now / tocando agora = $playing"

if [ -z "$(journalctl -k -n 1 -q 2>/dev/null)" ]; then
    echo "Can't read the kernel log. Run with sudo or join the 'adm' group. / Sem acesso ao log do kernel: use sudo."
    exit 1
fi
times=$(journalctl -k --since "-${MIN} min" --no-pager -q -o short-unix | grep "$SIG" | awk '{print int($1)}')
n=$(echo "$times" | grep -c .)
echo "Reboots:  $n in the last $MIN min / reinícios nos últimos $MIN min"
if [ "$n" -ge 2 ]; then
    med=$(echo "$times" | awk 'NR>1{print $1-p} {p=$1}' | sort -n | awk '{a[NR]=$1} END{print a[int((NR+1)/2)]}')
    echo "Interval: median ${med} s between reboots / mediana entre reinícios"
fi

guard=$(systemctl --user is-active alienware-headset-guard.service 2>/dev/null)
echo "Guard:    ${guard:-not installed}"

echo
if [ "$n" -ge 3 ] && [ "${med:-0}" -ge 120 ] && [ "${med:-0}" -le 180 ]; then
    echo "YES: same problem (reboot every ~2.5 min while audio plays)."
    echo "SIM: é o mesmo problema (reinicia a cada ~2,5 min com áudio tocando)."
    if [ "$guard" = active ]; then
        echo "The guard is already running: check a window that starts after it. / O protetor já roda: confira uma janela depois que ele começou."
    else
        echo "Fix / correção: ./install.sh"
    fi
elif [ "$n" -eq 0 ] && [ "$playing" = yes ]; then
    echo "OK: no reboots while playing. / OK: nenhum reinício com áudio tocando."
else
    echo "Inconclusive: play audio for $MIN min and run again. / Inconclusivo: toque áudio e rode de novo."
fi
