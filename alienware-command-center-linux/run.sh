#!/usr/bin/env bash
# Abre o Alienware Toolkit com o Python do .venv do repositório (criado pelo ../install.sh).
# Sem o .venv, usa o python3 do sistema (o app só precisa do PyGObject, GTK 4 e libadwaita do Ubuntu).
AQUI="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$AQUI" || exit 1
for py in "$AQUI/../.venv/bin/python" "$AQUI/.venv/bin/python"; do
    [ -x "$py" ] && exec "$py" "$AQUI/app.py" "$@"
done
exec python3 "$AQUI/app.py" "$@"
