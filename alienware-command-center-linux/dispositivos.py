"""Tudo o que o painel lê do sistema, fora o protocolo do mouse (que fica em aw720m.py).

- Lista de dispositivos USB (/sys/bus/usb/devices), atualizada pelo painel a cada 2 s.
- Headset AW725H: firmware, reinícios do dongle (journalctl), serviço de proteção e áudio (wpctl).

Só usa a biblioteca padrão e comandos do sistema (journalctl, systemctl, wpctl, pw-dump).
Cada função que chama um comando devolve um valor "vazio" se o comando falhar, sem travar o painel.
"""

import datetime
import glob
import json
import os
import subprocess

PASTA = os.path.dirname(os.path.abspath(__file__))

# ---------- dispositivos conhecidos ----------

# (vendor, product) -> (nome, tipo). Tipo decide a ilustração e a página que abre.
SUPORTADOS = {
    ("413c", "3029"): ("Alienware AW720M", "mouse"),
    ("413c", "3028"): ("Alienware AW720M", "mouse"),
    ("413c", "ab2b"): ("Alienware AW725H", "headset"),
    # Redragon K617 Fizz Rainbow (K617-R-B): só pré-visualização e leitura (ver teclado_sinowealth.py)
    ("258a", "002a"): ("Redragon K617 Fizz Rainbow", "teclado"),
}
# Nomes mais claros para aparelhos comuns que só mostram informações
NOMES_CONHECIDOS = {
    ("0e8d", "7961"): "MediaTek Wi-Fi MT7921U",
    ("413c", "a52a"): "Alienware AW725H (cabo USB-C)",  # o próprio headset ligado no cabo (carga)
}
MODO_MOUSE = {"3029": "Dongle 2.4G", "3028": "Cabo USB-C"}

# Firmware do headset: o mais recente publicado pela Dell (jul/2025, DSA-2025-303).
# Só atualiza no Windows, e sempre os dois juntos (headset e dongle).
FIRMWARE_RECENTE = "headset 1.8.0 + dongle 1.1.0"
URL_FIRMWARE = "https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=3gcwv"

def dongle_desatualizado(versao):
    """True se o bcdDevice do dongle (ex.: '1.00') for menor que 1.10, o provável número do dongle 1.1.0.

    A Dell não documenta essa correspondência; por isso a tela diz "provavelmente".
    """
    try:
        return tuple(int(x) for x in versao.split(".")) < (1, 10)
    except ValueError:
        return False


# Quando o chip do dongle reinicia, ele aparece por 1 s com este ID no log do kernel
MARCA_REINICIO = "idVendor=0e8d, idProduct=0003"

SERVICO_GUARDA = "alienware-headset-guard.service"
# Estado escrito pelo protetor (aw725h-headset-disconnect-fix/aw725h_guard.py), com chaves em inglês
ARQUIVO_GUARDA = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                              "aw725h-guard", "status.json")
# Pasta do conserto do headset no repositório (ao lado da pasta do app) e o guia dela
REPOSITORIO = os.path.dirname(PASTA)
PASTA_FIX = os.path.join(REPOSITORIO, "aw725h-headset-disconnect-fix")
GUIA_HEADSET = os.path.join(PASTA_FIX, "README.md")
SCRIPT_GUARDA = os.path.join(PASTA_FIX, "aw725h_guard.py")


def _ler(pasta, nome, padrao=""):
    """Lê um arquivo do sysfs (ex.: idVendor) sem quebrar se ele não existir."""
    try:
        with open(os.path.join(pasta, nome)) as f:
            return f.read().strip()
    except OSError:
        return padrao


def _rodar(comando, tempo=4):
    """Roda um comando e devolve (código de saída, texto). Código 127 = comando não existe."""
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=tempo)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, f"{comando[0]} não encontrado"
    except subprocess.TimeoutExpired:
        return 124, f"{comando[0]} demorou demais"


def velocidade_legivel(mbps):
    """'12' -> 'Full speed · 12 Mb/s' (nomes do padrão USB)."""
    nomes = {"1.5": "Low speed", "12": "Full speed", "480": "High speed",
             "5000": "SuperSpeed", "10000": "SuperSpeed+", "20000": "SuperSpeed+ 2x2"}
    if not mbps:
        return "desconhecida"
    valor = f"{int(mbps) // 1000} Gb/s" if mbps.isdigit() and int(mbps) >= 1000 else f"{mbps} Mb/s"
    return f"{nomes.get(mbps, 'USB')} · {valor.replace('.', ',')}"


def versao_bcd(bcd):
    """bcdDevice do USB em texto: '0100' -> '1.00', '0213' -> '2.13' (cada dígito já é decimal)."""
    if len(bcd) != 4 or not bcd.isdigit():
        return bcd or "?"
    return f"{int(bcd[:2])}.{bcd[2:]}"


def _interfaces(porta):
    """Lista as interfaces de um dispositivo: [(classe, protocolo, driver), ...]."""
    lista = []
    for pasta in sorted(glob.glob(f"/sys/bus/usb/devices/{porta}:*")):
        driver = os.path.basename(os.readlink(f"{pasta}/driver")) if os.path.exists(f"{pasta}/driver") else "-"
        lista.append((_ler(pasta, "bInterfaceClass"), _ler(pasta, "bInterfaceProtocol"), driver))
    return lista


def _tipo_generico(produto, interfaces):
    """Adivinha o tipo de um aparelho não suportado, só para escolher a ilustração."""
    classes = {(c, p) for c, p, _ in interfaces}
    if ("03", "01") in classes or "KB" in produto or "eyboard" in produto:
        return "teclado", "Teclado"
    if ("03", "02") in classes:
        return "usb", "Mouse"
    if any(c == "01" for c, _, _ in interfaces):
        return "usb", "Áudio"
    if any(c in ("e0", "ff") for c, _, _ in interfaces) and "ireless" in produto:
        return "usb", "Adaptador sem fio"
    return "usb", "Dispositivo USB"


def listar_usb():
    """Lista os aparelhos USB ligados, sem hubs. Cada item é um dicionário com tudo que a tela mostra."""
    lista = []
    for pasta in sorted(glob.glob("/sys/bus/usb/devices/*")):
        porta = os.path.basename(pasta)
        if ":" in porta or porta.startswith("usb"):
            continue  # interfaces (1-2:1.0) e root hubs (usb1) não são aparelhos
        vid, pid = _ler(pasta, "idVendor"), _ler(pasta, "idProduct")
        if not vid or _ler(pasta, "bDeviceClass") == "09":
            continue  # hubs
        fabricante = _ler(pasta, "manufacturer", "fabricante desconhecido")
        produto = _ler(pasta, "product", f"{vid}:{pid}")
        interfaces = _interfaces(porta)
        if (vid, pid) in SUPORTADOS:
            nome, tipo = SUPORTADOS[(vid, pid)]
            tipo_texto = {"mouse": "Mouse", "headset": "Headset", "teclado": "Teclado"}[tipo]
        else:
            nome = NOMES_CONHECIDOS.get((vid, pid), produto)
            tipo, tipo_texto = _tipo_generico(produto, interfaces)
        lista.append({
            "porta": porta,
            "id": f"{vid}:{pid}",
            "vid": vid,
            "pid": pid,
            "fabricante": " ".join(fabricante.split()),  # tira espaços duplos ("Dell   Inc")
            "produto": produto.strip(),
            "nome": nome.strip(),
            "tipo": tipo,
            "tipo_texto": tipo_texto,
            "suportado": (vid, pid) in SUPORTADOS,
            "velocidade": velocidade_legivel(_ler(pasta, "speed")),
            "versao": versao_bcd(_ler(pasta, "bcdDevice")),
            "classe": _ler(pasta, "bDeviceClass"),
            "modo": MODO_MOUSE.get(pid, ""),
            "interfaces": interfaces,
        })
    return lista


def achar_headset():
    """Devolve o item do headset em listar_usb(), ou None se o dongle não estiver ligado."""
    return next((d for d in listar_usb() if d["tipo"] == "headset"), None)


# ---------- headset: reinícios do dongle ----------

def reinicios_headset():
    """Conta os reinícios do dongle no log do kernel das últimas 24 h.

    Retorna {"hora": n na última hora, "dia": n em 24 h, "ultimo": "dd/mm HH:MM:SS" ou None,
             "por_hora": [24 contagens, da mais antiga para a mais recente], "erro": texto ou None}.
    """
    resultado = {"hora": 0, "dia": 0, "ultimo": None, "por_hora": [0] * 24, "erro": None}
    codigo, texto = _rodar(["journalctl", "-k", "--since", "-24 h", "--no-pager", "-o", "short-iso"], tempo=10)
    if codigo != 0:
        resultado["erro"] = texto.splitlines()[-1] if texto else f"journalctl saiu com {codigo}"
        return resultado
    agora = datetime.datetime.now().astimezone()
    for linha in texto.splitlines():
        if MARCA_REINICIO not in linha:
            continue
        # Linha: 2026-10-29T07:54:28-03:00 jorgemetri-H110 kernel: usb 1-2: New USB device ...
        try:
            quando = datetime.datetime.fromisoformat(linha.split()[0])
        except ValueError:
            continue
        horas_atras = (agora - quando).total_seconds() / 3600
        if horas_atras < 0 or horas_atras >= 24:
            continue
        resultado["dia"] += 1
        if horas_atras < 1:
            resultado["hora"] += 1
        resultado["por_hora"][23 - int(horas_atras)] += 1
        resultado["ultimo"] = quando.strftime("%d/%m %H:%M:%S")
    return resultado


# ---------- headset: serviço de proteção contra quedas ----------

def servico_existe():
    """True se a unit do usuário alienware-headset-guard.service estiver instalada."""
    return _rodar(["systemctl", "--user", "cat", SERVICO_GUARDA])[0] == 0


def servico_ligado():
    """True se o serviço estiver habilitado ou rodando."""
    ativo = _rodar(["systemctl", "--user", "is-active", SERVICO_GUARDA])[1] == "active"
    habilitado = _rodar(["systemctl", "--user", "is-enabled", SERVICO_GUARDA])[1] == "enabled"
    return ativo or habilitado


def ligar_servico(ligar):
    """Liga (enable --now) ou desliga (disable --now) o serviço. Devolve (ok, mensagem)."""
    acao = ["enable", "--now"] if ligar else ["disable", "--now"]
    codigo, texto = _rodar(["systemctl", "--user", *acao, SERVICO_GUARDA], tempo=15)
    return codigo == 0, texto or ("ligado" if ligar else "desligado")


def status_guarda():
    """Lê o JSON que o serviço de proteção escreve. Devolve um dicionário ou None.

    Chaves: active, interventions, last_intervention ("HH:MM:SS" ou None), resets_detected (None = sem
    acesso ao log do kernel), mode, since e updated ("AAAA-MM-DD HH:MM:SS").
    """
    try:
        with open(ARQUIVO_GUARDA) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------- headset: áudio (PipeWire) ----------

def nos_audio_headset():
    """Acha no PipeWire os nós de saída e entrada do AW725H (os ids mudam a cada reinício do dongle).

    Retorna {"saida", "entrada": id ou None, "saida_padrao", "entrada_padrao": bool, "erro": texto ou None}.
    """
    nos = {"saida": None, "entrada": None, "saida_padrao": False, "entrada_padrao": False, "erro": None}
    codigo, texto = _rodar(["pw-dump"], tempo=6)
    if codigo != 0:
        nos["erro"] = texto or "pw-dump falhou"
        return nos
    try:
        objetos = json.loads(texto)
    except ValueError:
        nos["erro"] = "pw-dump devolveu algo que não é JSON"
        return nos
    nomes = {}
    padrao = {}
    for obj in objetos:
        if obj.get("type") == "PipeWire:Interface:Node":
            props = (obj.get("info") or {}).get("props", {})
            nome = props.get("node.name", "")
            if "AW725H" not in nome + props.get("node.description", ""):
                continue
            if props.get("media.class") == "Audio/Sink":
                nos["saida"], nomes["saida"] = obj["id"], nome
            elif props.get("media.class") == "Audio/Source":
                nos["entrada"], nomes["entrada"] = obj["id"], nome
        elif obj.get("type") == "PipeWire:Interface:Metadata" and (obj.get("props") or {}).get("metadata.name") == "default":
            for item in obj.get("metadata") or []:
                valor = item.get("value")
                if isinstance(valor, dict):
                    padrao[item.get("key")] = valor.get("name")
    nos["saida_padrao"] = "saida" in nomes and padrao.get("default.audio.sink") == nomes["saida"]
    nos["entrada_padrao"] = "entrada" in nomes and padrao.get("default.audio.source") == nomes["entrada"]
    return nos


def ler_volume(no):
    """Devolve (volume de 0 a 1.5, mudo) do nó, ou (None, False) se não der para ler."""
    codigo, texto = _rodar(["wpctl", "get-volume", str(no)])
    if codigo != 0 or not texto.startswith("Volume:"):
        return None, False
    # Exemplo: "Volume: 0.75 [MUTED]"
    return float(texto.split()[1]), "[MUTED]" in texto


def definir_volume(no, volume):
    """Volume de 0 a 1 (1 = 100%)."""
    return _rodar(["wpctl", "set-volume", str(no), f"{volume:.2f}"])[0] == 0


def definir_mudo(no, mudo):
    return _rodar(["wpctl", "set-mute", str(no), "1" if mudo else "0"])[0] == 0


def definir_padrao(no):
    """Torna o nó a saída (ou entrada) padrão do sistema."""
    return _rodar(["wpctl", "set-default", str(no)])[0] == 0
