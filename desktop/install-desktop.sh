#!/usr/bin/env bash
# Instala o ícone, o atalho (.desktop), o favorito na dock e a extensão de hover do Alienware Toolkit.
# Não precisa de root: tudo vai para ~/.local/share e para as configurações do usuário.
#
# Uso:
#   ./install-desktop.sh [PASTA_DO_APP]   # PASTA_DO_APP tem o run.sh (padrão: ../alienware-command-center-linux)
#   ./install-desktop.sh --uninstall      # desfaz tudo
set -euo pipefail

APP_ID="io.github.jmetrimiranda.AlienwareToolkit"
UUID="alienware-toolkit-hover@jmetrimiranda.github.io"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DADOS="${XDG_DATA_HOME:-$HOME/.local/share}"
ICONES="$DADOS/icons/hicolor"
ATALHO="$DADOS/applications/$APP_ID.desktop"
EXTENSAO="$DADOS/gnome-shell/extensions/$UUID"

msg() { printf '\033[36m==>\033[0m %s\n' "$*"; }
aviso() { printf '\033[33m!!\033[0m %s\n' "$*" >&2; }
tem() { command -v "$1" >/dev/null 2>&1; }

# Lista do gsettings (formato GVariant, ex.: ['a.desktop', 'b.desktop']) -> um item por linha
lista_ler() { gsettings get org.gnome.shell "$1" 2>/dev/null | sed "s/^@as //; s/[][]//g; s/'//g; s/, */\n/g" | sed '/^$/d'; }
# Um item por linha -> lista GVariant
lista_gravar() {
    local chave="$1" itens
    itens="$(sed "/^$/d; s/.*/'&'/" | paste -sd, - | sed 's/,/, /g')"
    gsettings set org.gnome.shell "$chave" "[$itens]"
}
# Adiciona um item a uma lista do org.gnome.shell sem duplicar
lista_add() {
    local chave="$1" item="$2"
    tem gsettings || { aviso "gsettings não encontrado; pule a chave $chave"; return 0; }
    if lista_ler "$chave" | grep -qxF "$item"; then return 0; fi
    { lista_ler "$chave"; echo "$item"; } | lista_gravar "$chave"
}
lista_tirar() {
    local chave="$1" item="$2"
    tem gsettings || return 0
    lista_ler "$chave" | grep -qxF "$item" || return 0
    lista_ler "$chave" | grep -vxF "$item" | lista_gravar "$chave"
}

atualizar_caches() {
    if tem gtk-update-icon-cache && [ -d "$ICONES" ]; then
        # o índice precisa do index.theme; sem ele o comando reclama e o GNOME procura nos diretórios mesmo assim
        gtk-update-icon-cache -f -t "$ICONES" >/dev/null 2>&1 || true
    fi
    if tem update-desktop-database; then
        update-desktop-database "$DADOS/applications" >/dev/null 2>&1 || true
    fi
}

desinstalar() {
    msg "Removendo ícones"
    find "$ICONES" -path "*/apps/$APP_ID.png" -delete 2>/dev/null || true
    rm -f "$ICONES/scalable/apps/$APP_ID.svg" "$ICONES/symbolic/apps/$APP_ID-symbolic.svg"
    msg "Removendo atalho $ATALHO"
    rm -f "$ATALHO"
    msg "Tirando dos favoritos da dock"
    lista_tirar favorite-apps "$APP_ID.desktop"
    msg "Desligando e removendo a extensão $UUID"
    if tem gnome-extensions; then gnome-extensions disable "$UUID" >/dev/null 2>&1 || true; fi
    lista_tirar enabled-extensions "$UUID"
    rm -rf "$EXTENSAO"
    atualizar_caches
    msg "Pronto. Para a extensão sumir de vez da sessão atual (Wayland), saia e entre de novo."
}

instalar() {
    local app_dir="${1:-}"
    if [ -z "$app_dir" ]; then
        # sem parâmetro: no repositório, o app fica em ../alienware-command-center-linux (ao lado de desktop/)
        app_dir="$AQUI/../alienware-command-center-linux"
        [ -e "$app_dir/run.sh" ] || app_dir="$AQUI"
    fi
    app_dir="$(cd "$app_dir" 2>/dev/null && pwd)" || { aviso "Pasta do app não existe: $1"; exit 1; }
    [ -x "$app_dir/run.sh" ] || aviso "Não achei $app_dir/run.sh executável; o atalho vai apontar para ele mesmo assim."

    msg "Copiando ícones para $ICONES"
    for d in "$AQUI"/icons/hicolor/*/apps; do
        local tam
        tam="$(basename "$(dirname "$d")")"   # 48x48, scalable, symbolic...
        install -d "$ICONES/$tam/apps"
        install -m644 "$d"/* "$ICONES/$tam/apps/"
    done

    msg "Instalando atalho $ATALHO (Exec=$app_dir/run.sh)"
    install -d "$(dirname "$ATALHO")"
    # o caminho pode ter espaços: o Exec do .desktop pede aspas nesse caso
    local exec_linha="$app_dir/run.sh"
    case "$exec_linha" in *" "*) exec_linha="\"$exec_linha\"" ;; esac
    while IFS= read -r linha; do
        [ "$linha" = "Exec=@APPDIR@/run.sh" ] && linha="Exec=$exec_linha"
        printf '%s\n' "$linha"
    done < "$AQUI/$APP_ID.desktop" > "$ATALHO"
    chmod 644 "$ATALHO"
    atualizar_caches

    msg "Fixando na dock (favorite-apps)"
    lista_add favorite-apps "$APP_ID.desktop"

    msg "Instalando a extensão em $EXTENSAO"
    rm -rf "$EXTENSAO"
    install -d "$EXTENSAO"
    cp -r "$AQUI/extension/$UUID/." "$EXTENSAO/"

    # O shell só enxerga extensões novas depois de reiniciar a sessão; se o "enable" falhar,
    # gravamos direto na lista de extensões ligadas, e ela entra no próximo login.
    if tem gnome-extensions && gnome-extensions enable "$UUID" >/dev/null 2>&1; then
        msg "Extensão ligada"
    else
        lista_add enabled-extensions "$UUID"
        msg "Extensão marcada para ligar no próximo login"
    fi
    if tem gsettings && [ "$(gsettings get org.gnome.shell disable-user-extensions 2>/dev/null)" = "true" ]; then
        aviso "As extensões de usuário estão desligadas (disable-user-extensions = true). Ligue no app Extensões."
    fi
    echo
    msg "Pronto. No Wayland é preciso SAIR E ENTRAR na sessão uma vez para o GNOME Shell carregar a extensão."
    msg "Depois disso, passe o mouse sobre o ícone na dock."
}

case "${1:-}" in
    --uninstall|-u) desinstalar ;;
    --help|-h) sed -n '2,6p' "$0" ;;
    *) instalar "${1:-}" ;;
esac
