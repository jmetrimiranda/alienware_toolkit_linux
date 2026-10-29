"""Página do teclado Redragon K617 Fizz Rainbow (modelo K617-R-B, USB 258a:002a): prévia, atalhos Fn e leitura.

Situação (29/10/2026):
- Na versão Rainbow os LEDs têm COR FIXA DE FÁBRICA por fileira (vermelho, laranja, verde, azul, roxo).
  Pelas teclas Fn só se troca o modo, o brilho e a velocidade. O Linux não muda a cor.
- Não existe protocolo de escrita confiável para o 258a:002a (o OpenRGB desativou SinoWealth genérico depois
  de bricar teclados Redragon, e o report 5 também é o canal do bootloader). Por isso a página só
  PRÉ-VISUALIZA no 3D o que as teclas Fn fazem e LÊ os feature reports (teclado_sinowealth.py).
- Quem tem o K617 Fizz RGB (258a:0049) pode usar o fizz-rgb (github.com/MrSchrodingers/fizz-rgb).
"""

import os
import subprocess
import threading
import time

from gi.repository import GLib, Gtk

import k617_atalhos
import teclado_sinowealth as tk
from ui.pagina_base import PaginaDispositivo
from ui.widgets import dica, grade_info, rotulo

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORIO = os.path.dirname(PASTA)
DADOS = os.path.join(PASTA, "dados")
SCRIPT_PERMISSAO = os.path.join(REPOSITORIO, "udev", "install-udev-rules.sh")
DOC_PROTOCOLO = os.path.join(REPOSITORIO, "docs", "sinowealth-258a-002a-keyboard-protocol.md")
URL_FIZZ_RGB = "https://github.com/MrSchrodingers/fizz-rgb"

# Cores de fábrica por fileira do K617 Rainbow (de cima para baixo), como aparecem nas fotos do modelo -R
FILEIRAS = [("Fileira 1 · Esc e números", "#ff2a2a", "vermelho"),
            ("Fileira 2 · Tab e QWERTY", "#ffa412", "laranja"),
            ("Fileira 3 · Caps e ASDF", "#2ee05a", "verde"),
            ("Fileira 4 · Shift e ZXCV", "#13a8ff", "azul"),
            ("Fileira 5 · Ctrl e Espaço", "#9a4dff", "roxo")]

# Efeitos de pré-visualização (nome na tela, nome no 3D). No teclado real: Fn + Alt direito troca o modo.
EFEITOS = [("Fixo (cores de fábrica)", "fixo"), ("Respirar", "respirar"), ("Pulsar", "pulsar"),
           ("Onda arco-íris", "arco-iris"), ("Espectro", "espectro"), ("Apagado", "apagado")]
EFEITOS_DESCRICAO = {
    "fixo": "Cada fileira acesa na sua cor de fábrica, sem animação.",
    "respirar": "As fileiras acendem e apagam devagar, nas cores de fábrica.",
    "pulsar": "Piscadas curtas nas cores de fábrica.",
    "arco-iris": "Onda de cores correndo da esquerda para a direita (efeito comum nos modelos Rainbow).",
    "espectro": "O teclado inteiro passando por todas as cores.",
    "apagado": "Luz desligada (no teclado: Fn + M até apagar, se o seu modelo tiver esse nível).",
}
NIVEIS = 5  # brilho e velocidade têm 5 níveis no teclado (Fn + M e Fn + ,)
APAGADA = "#1d1f23"  # cor das teclas que não fazem parte do atalho destacado

RAINBOW_TEXTO = {"sim": "sim", "talvez": "talvez", "não": "não (só no RGB)"}


class PaginaTeclado(PaginaDispositivo):
    def __init__(self, janela):
        super().__init__(janela, "Redragon K617 Fizz", "Rainbow", "teclado-k617.svg", luz=(260, 90, 200),
                         modelo3d="teclado")
        self.info = None              # resultado de teclado_sinowealth.achar() (só sysfs)
        self.ultima_leitura = None    # última leitura dos reports (para comparar)
        self.lido_ao_conectar = False
        self.destaque = None          # atalho destacado no 3D (índice em ATALHOS) ou None

        if self.visualizador:
            self.visualizador.set_layout("k617")  # 60%, 61 teclas ANSI

        self.abas.adicionar("iluminacao", "Iluminação", self._aba_iluminacao(),
                            "Cores de fábrica por fileira e prévia no 3D do modo, do brilho e da velocidade que "
                            "as teclas Fn mudam. Nada é enviado ao teclado.")
        self.abas.adicionar("atalhos", "Atalhos Fn", self._aba_atalhos(),
                            "Tabela das combinações com a tecla Fn (manual do K617). Clique numa linha para "
                            "acender as teclas no 3D.")
        self.abas.adicionar("informacoes", "Informações", self._aba_informacoes(),
                            "Modelo, IDs, firmware, interfaces, privacidade e leitura (só leitura) dos reports.")
        self.abas.ao_trocar = self._aba_aberta

        self.definir_status("Somente pré-visualização e leitura: o painel não envia nada a este teclado.", True)
        self._atualizar_previa()
        self.atualizar_conexao()
        GLib.timeout_add_seconds(2, self.atualizar_conexao)

    # =====================================================================
    # Abas
    # =====================================================================

    def _aba_iluminacao(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

        # --- aviso honesto ---
        aviso = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["bloco"])
        aviso.append(rotulo("CORES FIXAS DE FÁBRICA", "secao"))
        aviso.append(rotulo(
            "Na versão Rainbow as cores dos LEDs são fixas de fábrica (uma por fileira); o Linux não muda cor. "
            "Pelas teclas Fn você troca o modo, o brilho e a velocidade. Se o seu for o K617 RGB (USB "
            "258a:0049), use o fizz-rgb.", "texto-ajuda", wrap=True))
        link = dica(Gtk.LinkButton(uri=URL_FIZZ_RGB, label="fizz-rgb (para o K617 RGB) ↗", halign=Gtk.Align.START),
                    "Abre no navegador o projeto fizz-rgb (MIT), de MrSchrodingers: controle de cor no Linux para o "
                    "K617 Fizz RGB (258a:0049). Ele NÃO serve para o Rainbow (258a:002a).")
        aviso.append(link)
        caixa.append(aviso)

        # --- cores por fileira ---
        caixa.append(rotulo("CORES DE FÁBRICA POR FILEIRA", "secao"))
        grade = Gtk.Grid(column_spacing=12, row_spacing=6)
        for i, (nome, cor, cor_nome) in enumerate(FILEIRAS):
            amostra = Gtk.Label(label="", width_request=34, height_request=16, css_classes=["fileira", f"fileira-{i + 1}"])
            dica(amostra, f"{nome}: LED {cor_nome} ({cor}), cor aproximada pela foto do modelo -R.")
            grade.attach(amostra, 0, i, 1, 1)
            grade.attach(rotulo(nome, "dim"), 1, i, 1, 1)
        caixa.append(grade)

        # --- efeito, brilho e velocidade (o que as teclas Fn fazem) ---
        caixa.append(rotulo("MODO (PRÉ-VISUALIZAÇÃO)", "secao", margin_top=4))
        linha = Gtk.Box(spacing=12)
        self.combo_efeito = dica(Gtk.DropDown.new_from_strings([e[0] for e in EFEITOS]),
                                 "Escolha um modo para ver no 3D como ele fica. No teclado, quem troca o modo é "
                                 "Fn + Alt direito (em ciclo). Nada é enviado ao teclado.")
        self.combo_efeito.set_size_request(230, -1)
        self.combo_efeito.connect("notify::selected", lambda *_a: self._atualizar_previa())
        linha.append(self.combo_efeito)
        self.rotulo_efeito = rotulo("", "texto-ajuda", wrap=True, hexpand=True)
        linha.append(self.rotulo_efeito)
        caixa.append(linha)

        self.brilho = self._nivel(caixa, "BRILHO", "Fn + M",
                                  "Brilho da prévia em 5 níveis, como o Fn + M do teclado (em ciclo).", NIVEIS)
        self.velocidade = self._nivel(caixa, "VELOCIDADE", "Fn + ,",
                                      "Velocidade da animação em 5 níveis, como o Fn + , do teclado (em ciclo).", 3)

        caixa.append(rotulo(
            "Esta aba só imita no 3D o que as teclas Fn fazem. Para controlar a cor pelo Linux seria preciso "
            "o protocolo USB do teclado, que ninguém publicou para o 258a:002a. O caminho é capturar o software "
            "oficial no Windows com USBPcap (veja a aba Informações). Contribuições são bem-vindas.",
            "texto-ajuda", wrap=True))
        return self.rolavel(caixa)

    def _nivel(self, caixa, titulo_nivel, teclas, explicacao, inicial):
        """Escala de 1 a 5 com o atalho do teclado ao lado."""
        linha = Gtk.Box(spacing=12)
        linha.append(rotulo(titulo_nivel, "secao", width_chars=11))
        escala = dica(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, NIVEIS, 1), explicacao)
        escala.set_hexpand(True)
        escala.set_round_digits(0)  # só valores inteiros (níveis 1 a 5)
        for n in range(1, NIVEIS + 1):
            escala.add_mark(n, Gtk.PositionType.BOTTOM, str(n))
        escala.set_value(inicial)
        escala.connect("value-changed", lambda _e: self._atualizar_previa())
        linha.append(escala)
        linha.append(dica(rotulo(teclas, "etiqueta", valign=Gtk.Align.CENTER),
                          f"No teclado: {teclas} (em ciclo, 5 níveis)."))
        caixa.append(linha)
        return escala

    def _aba_atalhos(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        caixa.append(rotulo(
            "Segure Fn e aperte a outra tecla. Fonte: manual do K617 Fizz RGB; no Rainbow algumas combinações "
            "podem não existir (coluna RAINBOW). Teste rápido: Fn + Espaço só faz algo no RGB. "
            "Clique numa linha para acender as teclas no 3D.", "texto-ajuda", wrap=True))
        self.rotulo_tecla = rotulo("", "ciano", wrap=True)
        caixa.append(self.rotulo_tecla)

        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["atalhos"])
        cabecalho = Gtk.Box(spacing=12, margin_start=10, margin_end=10, margin_top=4, margin_bottom=4)
        cabecalho.append(rotulo("TECLAS", "secao", width_chars=20))
        cabecalho.append(rotulo("FUNÇÃO", "secao", hexpand=True))
        cabecalho.append(rotulo("RAINBOW", "secao", width_chars=8))
        caixa.append(cabecalho)
        for item in k617_atalhos.ATALHOS:
            linha = Gtk.Box(spacing=12, margin_start=10, margin_end=10, margin_top=6, margin_bottom=6)
            linha.append(rotulo(item["teclas"], "mono", width_chars=20, wrap=True))
            linha.append(rotulo(item["funcao"], wrap=True, hexpand=True))
            classe = {"sim": "ciano", "talvez": "aviso", "não": "dim"}.get(item["rainbow"], "dim")
            linha.append(rotulo(RAINBOW_TEXTO.get(item["rainbow"], item["rainbow"]), classe, width_chars=8, wrap=True))
            dica(linha, f"{item['teclas']}: {item['funcao']}. No Rainbow: {RAINBOW_TEXTO.get(item['rainbow'])}. "
                        "Clique para acender essas teclas no 3D; clique de novo para voltar às cores de fábrica.")
            lista.append(linha)
        lista.connect("row-activated", lambda _l, linha: self.destacar_atalho(linha.get_index()))
        self.lista_atalhos = lista
        caixa.append(lista)
        return self.rolavel(caixa)

    def _aba_informacoes(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.caixa_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caixa.append(self.caixa_info)

        caixa.append(rotulo("PRIVACIDADE E SEGURANÇA", "secao", margin_top=8))
        caixa.append(rotulo(
            "• A interface 1 do teclado também carrega as teclas digitadas (NKRO, report 6). Por isso a regra udev "
            "principal NÃO libera o teclado; a leitura abaixo só funciona com a regra opcional "
            "udev/71-sinowealth-keyboard-optional.rules (./install.sh --keyboard-experimental). O painel só usa "
            "feature reports e nunca lê as teclas.\n"
            "• A interface 0 (teclado de boot) continua só do root.\n"
            "• O report 5 também é o canal do bootloader: o painel bloqueia qualquer escrita nele.",
            "texto-ajuda", wrap=True))

        caixa.append(rotulo("FERRAMENTAS (SÓ LEITURA)", "secao", margin_top=8))
        botoes = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=8,
                             max_children_per_line=4, homogeneous=False)
        self.botao_ler = self._botao_ferramenta(
            botoes, "Ler reports", self.ler,
            "Lê os feature reports 5, 9, 10, 11 e 12 (GET_FEATURE, sem efeito colateral), mostra o resumo no "
            "log e salva os bytes em dados/leitura-*.json.")
        self.botao_comparar = self._botao_ferramenta(
            botoes, "Ler e comparar", self.ler_e_comparar,
            "Lê de novo e mostra só os bytes que mudaram. Use assim: LER REPORTS, mude o modo ou o brilho pelas "
            "teclas Fn do teclado, LER E COMPARAR. É o jeito seguro de mapear os bytes sem escrever nada.")
        self.botao_backup = self._botao_ferramenta(
            botoes, "Salvar backup", self.backup,
            "Lê tudo e salva em dados/backup-*.json (e um .bin por report).")
        self._botao_ferramenta(
            botoes, "Abrir documentação", lambda: self._abrir_externo(DOC_PROTOCOLO),
            "Abre docs/sinowealth-258a-002a-keyboard-protocol.md: o que se sabe do protocolo e o plano de "
            "captura no Windows (USBPcap) para quem quiser contribuir.")
        caixa.append(botoes)

        self.log = dica(Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.CHAR,
                                     top_margin=8, bottom_margin=8, left_margin=10, right_margin=10),
                        "Log da página do teclado (também salvo em logs/teclado-AAAAMMDD.txt).")
        janela_log = Gtk.ScrolledWindow(child=self.log, css_classes=["log"])
        janela_log.set_size_request(-1, 140)
        caixa.append(janela_log)
        return self.rolavel(caixa)

    @staticmethod
    def _botao_ferramenta(caixa, texto, ao_clicar, explicacao):
        botao = dica(Gtk.Button(label=texto.upper(), css_classes=["contorno"]), explicacao)
        botao.connect("clicked", lambda _b: ao_clicar())
        caixa.append(botao)
        return botao

    def _aba_aberta(self, nome):
        if nome != "atalhos" and self.destaque is not None:
            self.destaque = None
            self.lista_atalhos.unselect_all()
            self._atualizar_previa()

    # =====================================================================
    # Prévia no 3D (ou halo no SVG)
    # =====================================================================

    def _efeito(self):
        return EFEITOS[self.combo_efeito.get_selected()][1]

    def _atualizar_previa(self):
        if not hasattr(self, "velocidade"):
            return  # ainda montando a tela
        efeito = self._efeito()
        self.rotulo_efeito.set_text(EFEITOS_DESCRICAO[efeito])
        brilho = 0 if efeito == "apagado" else round(self.brilho.get_value()) * 100 // NIVEIS
        velocidade = (round(self.velocidade.get_value()) - 1) * 25  # 1..5 -> 0..100
        if self.visualizador:
            self.visualizador.set_light("todas", FILEIRAS[0][1])
            for i, (_nome, cor, _cor_nome) in enumerate(FILEIRAS):
                self.visualizador.set_light(f"fileira{i + 1}", cor)
            self.visualizador.set_effect("fixo" if efeito == "apagado" else efeito, None, "#101114", velocidade)
            self.visualizador.set_brightness(brilho)
        elif self.ilustracao:
            self.ilustracao.definir_brilho((0x9a, 0x4d, 0xff), brilho / 100)

    def destacar_atalho(self, indice):
        """Acende no 3D só as teclas do atalho escolhido (clicar de novo volta às cores de fábrica)."""
        if indice == self.destaque:
            self.destaque = None
            self.lista_atalhos.unselect_all()
            self._atualizar_previa()
            return
        self.destaque = indice
        item = k617_atalhos.ATALHOS[indice]
        self.rotulo_tecla.set_text(f"{item['teclas']}: {item['funcao']}")
        if self.visualizador:
            self.visualizador.set_effect("fixo", None, None, 50)
            self.visualizador.set_brightness(100)
            self.visualizador.set_light("todas", APAGADA)
            for tecla in item["ids"]:
                self.visualizador.set_light(f"tecla:{tecla}", "#00c8d7" if tecla == "Fn" else "#ffffff")

    def ao_clicar_zona(self, zona):
        """Clique numa tecla do 3D: mostra a fileira (cor de fábrica) e o que ela faz com Fn."""
        if not zona.startswith("tecla:"):
            return
        tecla = zona.split(":", 1)[1]
        usos = [a for a in k617_atalhos.ATALHOS if tecla in a["ids"] and tecla != "Fn"]
        if tecla == "Fn":
            texto = "Tecla Fn: segure junto com outra tecla (tabela abaixo)."
        elif usos:
            texto = f"Tecla {tecla}: " + " · ".join(f"{a['teclas']} = {a['funcao']}" for a in usos)
        else:
            texto = f"Tecla {tecla}: sem função com Fn no manual."
        self.abas.mostrar("atalhos")
        self.rotulo_tecla.set_text(texto)
        if usos:
            indice = k617_atalhos.ATALHOS.index(usos[0])
            self.lista_atalhos.select_row(self.lista_atalhos.get_row_at_index(indice))
            self.destaque = None  # o clique na tecla destaca o primeiro atalho dela
            self.destacar_atalho(indice)

    # =====================================================================
    # Conexão (só sysfs) e leitura dos reports
    # =====================================================================

    def atualizar_conexao(self):
        info = tk.achar()  # só sysfs: não abre o aparelho
        if info is None:
            if self.info is not None:
                self.escrever_log("Teclado desconectado.")
            self.info, self.lido_ao_conectar = None, False
        else:
            if self.info is None or info["caminho"] != self.info["caminho"]:
                self.escrever_log(f"Teclado encontrado: interface 1 em {info['caminho']}, porta USB {info['porta']}.")
                self.lido_ao_conectar = False
            self.info = info
        self._mostrar_conexao()
        return True  # mantém o timer

    def _firmware(self):
        """bcdDevice '1209' -> '12.09'."""
        bcd = (self.info or {}).get("firmware", "?")
        return f"{bcd[:2]}.{bcd[2:]}" if len(bcd) == 4 else bcd

    def _mostrar_conexao(self):
        info = self.info
        if info is None:
            self.cabecalho.set_markup('USB  <span foreground="#5d636b">○</span> NÃO ENCONTRADO')
            self.subcabecalho.set_text("258a:002a desconectado · prévia funciona mesmo assim")
        else:
            self.cabecalho.set_markup('LUZ  <span foreground="#ffb020">▮</span> '
                                      '<span foreground="#ffffff">SÓ PRÉ-VISUALIZAÇÃO</span>')
            self.subcabecalho.set_text(f"conectado · 258a:002a · firmware {self._firmware()} · "
                                       f"{info['polling_hz'] or '?'} Hz · porta {info['porta']}")
        ligado = info is not None and info["permissao"]
        for botao in (self.botao_ler, self.botao_comparar, self.botao_backup):
            botao.set_sensitive(ligado)
        self._mostrar_info()

    def _mostrar_info(self):
        while (filho := self.caixa_info.get_first_child()):
            self.caixa_info.remove(filho)
        info = self.info
        pares = [("Modelo", "Redragon K617 Fizz Rainbow (K617-R-B): 60%, 61 teclas, ANSI (US), corpo preto"),
                 ("ID USB", "258a:002a (SINO WEALTH \"Gaming KB\"). O K617 RGB usa 258a:0049")]
        if info is None:
            pares.append(("Conexão", "não encontrado agora"))
        else:
            reports = ", ".join(f"{r}: {t} B" for r, t in info["reports"].items())
            pares += [
                ("Firmware", f"{self._firmware()} (bcdDevice)"),
                ("Conexão", f"USB {info['velocidade']} Mb/s · porta {info['porta']} · {info['polling_hz'] or '?'} Hz"),
                ("Interfaces", f"0 = teclado de boot {info.get('caminho_if0', '?')} (só root) · "
                               f"1 = recursos {info['caminho']}"),
                ("Leitura", "liberada (regra opcional 71 instalada)" if info["permissao"]
                            else "desligada (regra opcional 71 não instalada)"),
                ("Controlador", "Sinowealth SH68F90A / BYK901 (provável): descritor idêntico ao DK200"
                                if info["familia_byk901"] else "descritor diferente do conhecido"),
                ("Feature reports", reports or "?"),
            ]
        pares.append(("Escrita", "bloqueada: não há protocolo de escrita confiável para este modelo"))
        self.caixa_info.append(grade_info(pares))

    def escrever_log(self, texto):
        if not hasattr(self, "log"):
            return False
        linha = f"[{time.strftime('%H:%M:%S')}] {texto}\n"
        buffer = self.log.get_buffer()
        buffer.insert(buffer.get_end_iter(), linha)
        if "ALIENWARE_CAPTURA" not in os.environ and "ALIENWARE_DEMO" not in os.environ:
            os.makedirs(os.path.join(PASTA, "logs"), exist_ok=True)
            with open(os.path.join(PASTA, "logs", f"teclado-{time.strftime('%Y%m%d')}.txt"), "a") as f:
                f.write(linha)
        self.log.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 0)
        return False  # para o GLib.idle_add não repetir

    def _ler_em_segundo_plano(self, prefixo, ao_terminar):
        """GET_FEATURE dos reports numa thread (o report 12 tem 1920 bytes) e volta na tela."""
        caminho = self.info["caminho"]

        def rodar():
            try:
                leitura = tk.ler_config(caminho)
                arquivo = tk.salvar_leitura(leitura, DADOS, prefixo) if prefixo else None
                GLib.idle_add(ao_terminar, leitura, arquivo)
            except (OSError, tk.SemPermissao) as erro:
                GLib.idle_add(self.escrever_log, f"Erro na leitura: {erro}")

        threading.Thread(target=rodar, daemon=True).start()

    def _resumir(self, leitura):
        for rid, item in tk.interpretar_config(leitura).items():
            if "erro" in item:
                self.escrever_log(f"report {rid}: ERRO {item['erro']}")
            else:
                self.escrever_log(f"report {rid}: {item['tamanho']} B, {item['zeros']} zeros, "
                                  f"faixas {item['faixas'][:4]} · {item['inicio']}")

    def ler(self):
        def terminar(leitura, arquivo):
            self.ultima_leitura = leitura
            self._resumir(leitura)
            self.escrever_log(f"Leitura feita ({len(leitura['reports'])} reports), salva em "
                              f"{os.path.relpath(arquivo, PASTA)}.")
            return False

        self._ler_em_segundo_plano("leitura", terminar)

    def ler_e_comparar(self):
        anterior = self.ultima_leitura

        def terminar(leitura, arquivo):
            self.ultima_leitura = leitura
            if anterior is None:
                self.escrever_log("Primeira leitura guardada; mude o modo pelas teclas Fn e compare de novo.")
                return False
            mudancas = tk.comparar(anterior, leitura)
            if not mudancas:
                self.escrever_log("Nenhum byte mudou desde a leitura anterior.")
            for rid, lista in mudancas.items():
                trecho = ", ".join(f"[{p}] {a:02x}→{d:02x}" for p, a, d in lista[:12]
                                   if a is not None and d is not None)
                self.escrever_log(f"report {rid}: {len(lista)} byte(s) mudaram: {trecho}"
                                  f"{' ...' if len(lista) > 12 else ''}")
            return False

        self._ler_em_segundo_plano("leitura", terminar)

    def backup(self):
        def terminar(leitura, arquivo):
            self.ultima_leitura = leitura
            self.escrever_log(f"Backup salvo em {os.path.relpath(arquivo, PASTA)}.")
            return False

        self._ler_em_segundo_plano("backup", terminar)

    def _abrir_externo(self, caminho):
        try:
            subprocess.Popen(["xdg-open", caminho])
        except OSError as erro:
            self.escrever_log(f"Não consegui abrir {caminho}: {erro}")

    def ao_mostrar(self):
        super().ao_mostrar()
        self.atualizar_conexao()
