#!/usr/bin/env bash
# Abre o teste guiado do mouse AW720M (só leitura). Rodar em um terminal.
cd "$(dirname "$(readlink -f "$0")")"
PY=../.venv/bin/python
[ -x "$PY" ] || PY=python3
echo "Teste guiado do AW720M: siga as instruções que aparecem. Nada é enviado ao mouse."
read -rp "Aperte Enter para começar... "
"$PY" sondar.py guiado
read -rp "Pronto! Aperte Enter para fechar. "
