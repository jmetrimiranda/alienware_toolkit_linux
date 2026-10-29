#!/usr/bin/env bash
# Conta quantas vezes o dongle do headset AW725H reiniciou (o chip aparece como 0e8d:0003 ao reiniciar).
# Uso: ./monitor_headset.sh [minutos]   (padrão: 30)
MIN=${1:-30}
n=$(journalctl -k --since "-${MIN} min" --no-pager 2>/dev/null | grep -c 'idVendor=0e8d, idProduct=0003')
ultimo=$(journalctl -k --since "-${MIN} min" --no-pager -o short-iso 2>/dev/null | grep 'idVendor=0e8d, idProduct=0003' | tail -1 | cut -c12-19)
porta=$(grep -l ab2b /sys/bus/usb/devices/*/idProduct 2>/dev/null | head -1 | xargs -r dirname)
echo "Reinícios do dongle nos últimos ${MIN} min: ${n}${ultimo:+ (último às $ultimo)}"
[ -n "$porta" ] && echo "Dongle na porta $(basename $porta), velocidade $(cat $porta/speed) Mb/s, firmware $(cat $porta/bcdDevice)"
echo "Esperado com o problema: ~$((MIN*60/150)) reinícios se houver áudio tocando o tempo todo."
