"""Teclado SINO WEALTH "Gaming KB" (USB 258a:002a) pelo hidraw do Linux.

O aparelho tem 2 interfaces HID:
  0 = teclado de boot (só root; o painel nunca abre essa interface);
  1 = sistema, multimídia, NKRO (report 6), "mouse" (report 13) e os feature reports
      de fabricante 5 (5 bytes), 9 (504), 10 (41), 11 (126) e 12 (1920).

O descritor da interface 1 é IDÊNTICO, byte a byte, ao do teclado DK200 (MCU BYK901,
Sinowealth SH68F90A) da issue #1804 do OpenRGB. Ver docs/sinowealth-258a-002a-keyboard-protocol.md.

SEGURANÇA (regra do projeto):
- Ler (GET_FEATURE) é seguro e não muda nada no teclado.
- O report 5 da interface 1 é o canal de ISP/bootloader do sinowealth-kb-tool:
  "05 75 00 00 00 00" reinicia o teclado no modo de gravação de firmware. Este módulo
  NUNCA escreve no report 5.
- Não existe fonte confiável com o protocolo de ESCRITA (cor/efeito) para este layout.
  Por isso PROTOCOLO_CONFIRMADO = False e todas as funções definir_* recusam enviar.
  Elas montam e mostram o que seria enviado só quando houver comandos capturados
  do software oficial (tabela COMANDOS, vazia por enquanto).
"""

import array
import fcntl
import glob
import json
import os
import time

VENDOR = 0x258A
PRODUTO = 0x002A

# Feature reports da interface 1: id -> tamanho em bytes SEM o byte do id
REPORTS = {5: 5, 9: 504, 10: 41, 11: 126, 12: 1920}
LEITURA_SEGURA = (5, 9, 10, 11, 12)  # só GET_FEATURE

# Descritor da interface 1 (269 bytes): igual ao do DK200/BYK901 (OpenRGB #1804)
DESCRITOR_FAMILIA = bytes.fromhex(
    "05010980a1018501198129831500250175019503810295058101c0050c0901a101850219002a3c0215"
    "00263c02950175108100c00600ff0901a1018505150026ff001901290275089505b102c005010906a1"
    "01850605071904297015002501750195788102c00600ff0901a1018509150026ff000900750896f801"
    "b102c00600ff0901a101850a150026ff00090075089529b102c00600ff0901a101850b150026ff0009"
    "007508957eb102c005010902a101850d0901a10005091500250119012905750195058102950381010501"
    "16008026ff7f093009317510950281061581257f0938750895018106050c0a380295018106c0c00600"
    "ff0901a101850c150026ff0009007508968007b102c0")

# ---------------------------------------------------------------------------
# Trava de segurança da escrita
# ---------------------------------------------------------------------------
PROTOCOLO_CONFIRMADO = False  # só vira True com comandos capturados do software oficial
REPORT_ISP = 5                # canal de ISP/bootloader (sinowealth-kb-tool): nunca escrever
BYTES_PROIBIDOS_REPORT5 = {   # comandos de ISP/firmware conhecidos (sinowealth-kb-tool, libratbag)
    0x75: "entrar no modo ISP/DFU (bootloader)",
    0x55: "habilitar firmware (ISP)",
    0x52: "iniciar leitura da flash (ISP)",
    0x57: "iniciar gravação da flash (ISP)",
    0x45: "apagar a flash (ISP)",
    0x5A: "reiniciar (ISP)",
}

# Comandos de escrita confirmados: VAZIO. Preencher só a partir de uma captura USBPcap do
# software oficial deste teclado (ver docs/, seção "Windows capture plan").
# Formato esperado: nome -> {"report": id, "modelo": bytes com marcadores, "fonte": "..."}
COMANDOS = {}

# Opções que a interface mostra como PRÉVIA (nomes comuns nesses teclados, não confirmados)
EFEITOS = ["fixo", "respirar", "onda", "arco-íris", "reativo", "ondulação", "desligado"]
DIRECOES = ["esquerda → direita", "direita → esquerda"]
NIVEIS_BRILHO = 5     # 0..4 nos teclados Sinowealth documentados (OpenRGB, GK850)
NIVEIS_VELOCIDADE = 5  # 0..4 idem

# ioctl do hidraw (linux/hidraw.h): _IOC(_IOC_READ|_IOC_WRITE, 'H', nr, tamanho)
_IOC_RW = 3


def _hidioc(nr, tamanho):
    return (_IOC_RW << 30) | (tamanho << 16) | (ord("H") << 8) | nr


def HIDIOCGFEATURE(tamanho):
    return _hidioc(0x07, tamanho)


def HIDIOCSFEATURE(tamanho):
    return _hidioc(0x06, tamanho)


class SemPermissao(Exception):
    """O /dev/hidrawN existe, mas o usuário não pode abrir (falta a regra udev)."""


class ProtocoloNaoConfirmado(Exception):
    """Pedido de escrita sem comando confirmado: nada foi enviado ao teclado."""


class EscritaBloqueada(Exception):
    """Pedido de escrita que poderia mexer no bootloader/firmware: bloqueado sempre."""


def hexa(dados):
    return " ".join(f"{b:02x}" for b in dados)


# ---------------------------------------------------------------------------
# Achar o teclado
# ---------------------------------------------------------------------------

def _ler(caminho, binario=False):
    try:
        with open(caminho, "rb" if binario else "r") as f:
            return f.read() if binario else f.read().strip()
    except OSError:
        return None


def achar():
    """Procura o teclado no sysfs (não abre nada).

    Retorna um dicionário com caminho (interface 1), caminho_if0, porta USB, firmware (bcdDevice),
    velocidade, polling em Hz e se o descritor é o da família BYK901; ou None se não estiver ligado.
    """
    achado = {}
    for pasta in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = _ler(f"{pasta}/device/uevent") or ""
        linha = next((l for l in uevent.splitlines() if l.startswith("HID_ID=")), None)
        if not linha:
            continue
        _, vid, pid = linha.split("=")[1].split(":")
        if int(vid, 16) != VENDOR or int(pid, 16) != PRODUTO:
            continue
        # .../usb1/1-3/1-3:1.1/0003:258A:002A.0004 -> interface "1-3:1.1"
        interface = os.path.basename(os.path.dirname(os.path.realpath(f"{pasta}/device")))
        numero = interface.rsplit(".", 1)[-1]
        no = f"/dev/{os.path.basename(pasta)}"
        if numero == "0":
            achado["caminho_if0"] = no
            continue
        usb = os.path.dirname(os.path.dirname(os.path.realpath(f"{pasta}/device")))
        descritor = _ler(f"{pasta}/device/report_descriptor", binario=True) or b""
        intervalo = _ler(f"{usb}/{interface}/ep_82/bInterval")  # endpoint da interface 1
        achado.update(
            caminho=no,
            porta=os.path.basename(usb),
            fabricante=_ler(f"{usb}/manufacturer") or "?",
            produto=_ler(f"{usb}/product") or "?",
            firmware=_ler(f"{usb}/bcdDevice") or "?",
            velocidade=_ler(f"{usb}/speed") or "?",
            polling_hz=round(1000 / int(intervalo, 16)) if intervalo and int(intervalo, 16) else None,
            descritor=descritor,
            familia_byk901=(descritor == DESCRITOR_FAMILIA),
            reports=_reports_do_descritor(descritor),
        )
    if "caminho" not in achado:
        return None
    achado["permissao"] = os.access(achado["caminho"], os.R_OK | os.W_OK)
    return achado


def _reports_do_descritor(descritor):
    """Lista os feature reports (id -> bytes) declarados no descritor HID (parser simples)."""
    reports, i, rid, tam, qtd = {}, 0, 0, 0, 0
    while i < len(descritor):
        prefixo = descritor[i]
        n = {0: 0, 1: 1, 2: 2, 3: 4}[prefixo & 3]
        valor = int.from_bytes(descritor[i + 1:i + 1 + n], "little")
        item = prefixo & 0xFC
        if item == 0x84:
            rid = valor
        elif item == 0x74:
            tam = valor
        elif item == 0x94:
            qtd = valor
        elif item == 0xB0:  # Feature
            reports[rid] = reports.get(rid, 0) + tam * qtd // 8
        i += 1 + n
    return reports


# ---------------------------------------------------------------------------
# Leitura (segura)
# ---------------------------------------------------------------------------

def _abrir(caminho, escrita=False):
    try:
        return os.open(caminho, os.O_RDWR if escrita else os.O_RDONLY)
    except PermissionError as erro:
        raise SemPermissao(f"sem permissão para abrir {caminho} (falta a regra udev)") from erro


def ler_report(fd, rid):
    """GET_FEATURE de um report. Devolve os bytes SEM o id (pode vir menor que o declarado)."""
    tamanho = REPORTS[rid] + 1
    buf = array.array("B", [rid] + [0] * (tamanho - 1))
    n = fcntl.ioctl(fd, HIDIOCGFEATURE(tamanho), buf, True)
    dados = bytes(buf[:n])
    # O hidraw devolve o id no primeiro byte quando o aparelho usa report IDs
    return dados[1:] if dados[:1] == bytes([rid]) else dados


def ler_config(caminho=None, reports=LEITURA_SEGURA):
    """Lê os feature reports (só GET_FEATURE, sem efeito colateral).

    Retorna {"quando", "caminho", "firmware", "reports": {id: bytes}, "erros": {id: texto}}.
    """
    info = achar() if caminho is None else {"caminho": caminho}
    if info is None:
        raise FileNotFoundError("teclado 258a:002a não encontrado")
    fd = _abrir(info["caminho"])  # somente leitura: write() nem é possível neste fd
    leitura = {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "caminho": info["caminho"],
               "firmware": info.get("firmware"), "reports": {}, "erros": {}}
    try:
        for rid in reports:
            try:
                leitura["reports"][rid] = ler_report(fd, rid)
            except OSError as erro:
                leitura["erros"][rid] = str(erro)
    finally:
        os.close(fd)
    return leitura


def salvar_leitura(leitura, pasta, prefixo="leitura"):
    """Salva os bytes crus (.bin por report) e um .json com tudo em hexadecimal. Devolve o .json."""
    os.makedirs(pasta, exist_ok=True)
    carimbo = time.strftime("%Y%m%d-%H%M%S")
    for rid, dados in leitura["reports"].items():
        with open(os.path.join(pasta, f"{prefixo}-{carimbo}-report{rid:02d}.bin"), "wb") as f:
            f.write(dados)
    arquivo = os.path.join(pasta, f"{prefixo}-{carimbo}.json")
    with open(arquivo, "w") as f:
        json.dump({"quando": leitura["quando"], "caminho": leitura["caminho"], "firmware": leitura.get("firmware"),
                   "reports": {str(r): d.hex() for r, d in leitura["reports"].items()},
                   "erros": {str(r): e for r, e in leitura["erros"].items()}}, f, indent=1)
    return arquivo


def carregar_leitura(arquivo):
    with open(arquivo) as f:
        dados = json.load(f)
    dados["reports"] = {int(r): bytes.fromhex(h) for r, h in dados["reports"].items()}
    dados["erros"] = {int(r): e for r, e in dados.get("erros", {}).items()}
    return dados


# ---------------------------------------------------------------------------
# Interpretação (mapa dos bytes)
# ---------------------------------------------------------------------------

def trechos_nao_nulos(dados, folga=2):
    """Faixas [início, fim) com bytes diferentes de 0x00 e de 0xFF (juntando buracos de até 'folga')."""
    faixas, inicio, ultimo = [], None, None
    for i, b in enumerate(dados):
        if b not in (0x00, 0xFF):
            if inicio is None:
                inicio = i
            elif i - ultimo > folga + 1:
                faixas.append((inicio, ultimo + 1))
                inicio = i
            ultimo = i
    if inicio is not None:
        faixas.append((inicio, ultimo + 1))
    return faixas


def interpretar_config(leitura):
    """Resumo legível de cada report: tamanho, faixas com dados e o que já se sabe.

    O significado de cada byte de escrita NÃO é conhecido; aqui só há o que dá para afirmar
    olhando os bytes lidos (ver docs/ para o mapa completo).
    """
    resumo = {}
    for rid, dados in sorted(leitura["reports"].items()):
        cheios = sum(1 for b in dados if b == 0xFF)
        zeros = sum(1 for b in dados if b == 0x00)
        item = {
            "tamanho": len(dados),
            "esperado": REPORTS.get(rid),
            "zeros": zeros,
            "ff": cheios,
            "faixas": trechos_nao_nulos(dados),
            "inicio": hexa(dados[:16]),
            "papel": PAPEL_DOS_REPORTS.get(rid, "?"),
        }
        resumo[rid] = item
    for rid, erro in leitura.get("erros", {}).items():
        resumo[rid] = {"erro": erro, "papel": PAPEL_DOS_REPORTS.get(rid, "?")}
    return resumo


# Papel provável de cada report (hipóteses; grau de confiança no docs/)
PAPEL_DOS_REPORTS = {
    5: "comando curto (6 bytes com o id). Também é o canal de ISP: nunca escrever.",
    9: "bloco de 504 bytes (0x01F8): provável tabela de teclas/macros (504 = 126 × 4 ou 168 × 3).",
    10: "bloco de 41 bytes: provável configuração geral (efeito, brilho, velocidade, direção).",
    11: "bloco de 126 bytes: provável cor/tabela auxiliar (126 = 42 × 3 bytes RGB).",
    12: "bloco de 1920 bytes: provável mapa de cores por tecla (1920 = 640 × 3, ou 128 × 15).",
}


def comparar(antes, depois):
    """Diferenças byte a byte entre duas leituras: {id: [(posição, antes, depois), ...]}."""
    mudancas = {}
    for rid in sorted(set(antes["reports"]) | set(depois["reports"])):
        a, d = antes["reports"].get(rid, b""), depois["reports"].get(rid, b"")
        lista = [(i, a[i] if i < len(a) else None, d[i] if i < len(d) else None)
                 for i in range(max(len(a), len(d)))
                 if (a[i] if i < len(a) else None) != (d[i] if i < len(d) else None)]
        if lista:
            mudancas[rid] = lista
    return mudancas


# ---------------------------------------------------------------------------
# Escrita (TRAVADA até haver protocolo confirmado)
# ---------------------------------------------------------------------------

def verificar_escrita(rid, dados):
    """Confere um pedido de SET_FEATURE. Levanta exceção se não puder ir ao teclado."""
    if rid == REPORT_ISP:
        motivo = BYTES_PROIBIDOS_REPORT5.get(dados[0] if dados else None, "report 5 é o canal de ISP")
        raise EscritaBloqueada(f"escrita no report 5 bloqueada sempre ({motivo})")
    if rid not in REPORTS or len(dados) != REPORTS[rid]:
        raise EscritaBloqueada(f"report {rid} com {len(dados)} bytes não bate com o descritor")
    if not PROTOCOLO_CONFIRMADO:
        raise ProtocoloNaoConfirmado(
            "protocolo de escrita deste teclado não confirmado: nada foi enviado "
            "(ver docs/sinowealth-258a-002a-keyboard-protocol.md)")


def _enviar(caminho, rid, dados):
    """SET_FEATURE com todas as travas. Hoje sempre recusa (PROTOCOLO_CONFIRMADO = False)."""
    verificar_escrita(rid, dados)
    fd = _abrir(caminho, escrita=True)
    try:
        buf = array.array("B", bytes([rid]) + bytes(dados))
        fcntl.ioctl(fd, HIDIOCSFEATURE(len(buf)), buf, True)
    finally:
        os.close(fd)


def _comando(nome, **valores):
    """Monta um comando da tabela COMANDOS. Sem comando confirmado, recusa sem enviar nada."""
    if nome not in COMANDOS:
        raise ProtocoloNaoConfirmado(
            f"comando '{nome}' ainda não foi capturado do software oficial: nada foi enviado")
    modelo = COMANDOS[nome]
    return modelo["report"], modelo["montar"](**valores)


def definir_efeito(efeito, caminho=None):
    rid, dados = _comando("efeito", efeito=efeito)
    _enviar(caminho or achar()["caminho"], rid, dados)


def definir_cor(r, g, b, caminho=None):
    rid, dados = _comando("cor", r=r, g=g, b=b)
    _enviar(caminho or achar()["caminho"], rid, dados)


def definir_brilho(nivel, caminho=None):
    rid, dados = _comando("brilho", nivel=nivel)
    _enviar(caminho or achar()["caminho"], rid, dados)


def definir_velocidade(nivel, caminho=None):
    rid, dados = _comando("velocidade", nivel=nivel)
    _enviar(caminho or achar()["caminho"], rid, dados)


def definir_direcao(direcao, caminho=None):
    rid, dados = _comando("direcao", direcao=direcao)
    _enviar(caminho or achar()["caminho"], rid, dados)


def definir_cor_por_tecla(cores, caminho=None):
    """cores = {indice_do_led: (r, g, b)}. O mapa índice → tecla também depende da captura."""
    rid, dados = _comando("cor_por_tecla", cores=cores)
    _enviar(caminho or achar()["caminho"], rid, dados)


def restaurar(backup, caminho=None):
    """Devolve ao teclado os reports de um backup (dicionário de ler_config ou arquivo .json).

    Também passa pelas travas: hoje recusa, porque reescrever um report sem saber o que ele
    faz (pode gravar na flash) também é escrita não confirmada. Como nada foi escrito,
    não há o que restaurar.
    """
    if isinstance(backup, str):
        backup = carregar_leitura(backup)
    destino = caminho or achar()["caminho"]
    for rid, dados in sorted(backup["reports"].items()):
        if rid == REPORT_ISP:
            continue  # o report 5 nunca é escrito, nem para restaurar
        _enviar(destino, rid, dados)


if __name__ == "__main__":
    # Uso rápido: python3 teclado_sinowealth.py  -> mostra o aparelho e o resumo da leitura
    info = achar()
    if info is None:
        print("teclado 258a:002a não encontrado")
    else:
        print({k: v for k, v in info.items() if k != "descritor"})
        if info["permissao"]:
            for rid, item in interpretar_config(ler_config(info["caminho"])).items():
                print(rid, item)
        else:
            print("sem permissão no", info["caminho"], "(regra udev ainda não aplicada)")
