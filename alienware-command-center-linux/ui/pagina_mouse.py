"""Página do mouse Alienware AW720M: iluminação, bateria e diagnóstico.

Toda a conversa com o mouse passa por aw720m.py. Esta página:
- procura o mouse a cada 2 s (dongle ou cabo) e abre a interface de fabricante;
- deixa uma segunda leitura aberta só para receber o aviso de energia (c0 0a), que vira a bateria;
- só envia cor quando você clica em APLICAR.
"""

import json
import os
import subprocess
import threading
import time

from gi.repository import Adw, Gdk, GLib, Gtk

import aw720m
from ui.pagina_base import PaginaDispositivo
from ui.widgets import (AnelBateria, PreviaCor, RodaDeCores, dica, hex_para_rgb, rgb_para_hex,
                        rotulo)

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORIO = os.path.dirname(PASTA)
SCRIPT_PERMISSAO = os.path.join(REPOSITORIO, "udev", "install-udev-rules.sh")  # roda com pkexec
TESTE_GUIADO = os.path.join(REPOSITORIO, "tools", "teste_guiado.sh")
ARQUIVO_BATERIA = os.path.join(PASTA, "logs", "bateria.json")  # último aviso de energia recebido

# Cores 100% saturadas: no LED ficam fortes como no arco-íris (cores pastel ficam "lavadas")
AMOSTRAS = [
    ("Ciano Alienware", (0x00, 0xE5, 0xFF)),
    ("Vermelho", (0xFF, 0x00, 0x00)),
    ("Verde", (0x00, 0xFF, 0x00)),
    ("Azul", (0x00, 0x00, 0xFF)),
    ("Roxo", (0x80, 0x00, 0xFF)),
    ("Magenta", (0xFF, 0x00, 0xFF)),
    ("Laranja", (0xFF, 0x80, 0x00)),
    ("Branco", (0xFF, 0xFF, 0xFF)),
]

# Zonas: no AW610M 0 = luz e 1 = logo; no AW720M ainda não foi confirmado qual é qual
ZONAS = [("Zona A", [0], "Envia só para a zona 0. No AW610M a zona 0 é a luz; no AW720M ainda não confirmado."),
         ("Zona B", [1], "Envia só para a zona 1. No AW610M a zona 1 é o logo; no AW720M ainda não confirmado."),
         ("Ambas", [0, 1], "Envia o mesmo comando para as zonas 0 e 1 (recomendado enquanto as zonas do "
                           "AW720M não forem confirmadas).")]

EFEITOS_DESCRICAO = {
    "fixo": "Cor parada, sempre acesa. É o que deixa a cor mais forte.",
    "respirar": "Acende e apaga devagar. No meio do ciclo o LED fica fraco, então a cor parece mais rala.",
    "transição": "Alterna entre a cor principal e a 2ª cor.",
    "espectro": "Passa por todas as cores sozinho (a cor escolhida normalmente é ignorada).",
    "pulsar": "Pisca na cor escolhida. Como fica parte do tempo apagado, parece mais fraco que o fixo.",
    "arco-íris": "Onda de cores 100% saturadas (a cor escolhida normalmente é ignorada).",
}


def _css_amostras():
    """Cria uma classe CSS por amostra (ex.: .amostra-00e5ff { background: #00e5ff })."""
    regras = "".join(f"button.amostra-{rgb_para_hex(rgb)[1:].lower()} {{ background: {rgb_para_hex(rgb)}; }}\n"
                     for _, rgb in AMOSTRAS)
    provedor = Gtk.CssProvider()
    provedor.load_from_string(regras)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provedor,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)


def cor_lavada(rgb):
    """Simula como uma cor aparece no LED SEM a correção (mais clara/esbranquiçada)."""
    return tuple(round(255 * (c / 255) ** (1 / 2.2)) for c in rgb)


class PaginaMouse(PaginaDispositivo):
    def __init__(self, janela):
        super().__init__(janela, "AW720M", "Mouse", "mouse.svg", luz=(150, 318, 78), camada_luz="#logo",
                         modelo3d="mouse")
        _css_amostras()
        self.mouse = None  # aw720m.Mouse aberto, ou None
        self.info = None  # resultado de aw720m.achar()
        self.sem_permissao = False
        self.ocupado = False  # True enquanto uma escuta de 10 s roda
        self.ouvinte = None  # thread que espera os avisos de energia do mouse
        self.bateria = None  # {"bateria", "carregando", "quando"} do último aviso
        self.atualizando = False  # evita que mudanças feitas pelo código disparem eventos
        self.rgb = AMOSTRAS[0][1]
        self.rgb2 = (0xFF, 0x00, 0x00)

        # Aviso de permissão (aparece só quando falta a regra udev)
        self.aviso = Adw.Banner(title="Sem permissão para falar com o mouse (falta a regra udev)",
                                button_label="Dar permissão")
        dica(self.aviso, "Instala a regra udev/70-alienware-toolkit.rules com pkexec (pede a sua senha uma vez). "
                         "Depois disso o painel abre o mouse e o headset sem sudo.")
        self.aviso.connect("button-clicked", lambda _b: self.dar_permissao())
        self.avisos.append(self.aviso)

        self.abas.adicionar("iluminacao", "Iluminação", self._aba_iluminacao(),
                            "Cor, zonas, efeito e brilho do LED. Nada é enviado até você clicar em APLICAR.")
        self.abas.adicionar("bateria", "Bateria", self._aba_bateria(),
                            "Último nível de bateria avisado pelo mouse e se está carregando.")
        self.abas.adicionar("diagnostico", "Diagnóstico", self._aba_diagnostico(),
                            "Ferramentas de investigação do protocolo e o log do painel.")

        self.botao_barra("✕  CANCELAR", "cancelar",
                         "Volta os controles para a última configuração aplicada. Não envia nada ao mouse.",
                         self.cancelar)
        self.botao_aplicar = self.botao_barra(
            "✓  APLICAR", "aplicar",
            "Envia a cor, a zona, o efeito e o brilho ao mouse agora (comando 40 10 do protocolo APIv7). "
            "A configuração fica no mouse até você mudar de novo.", self.aplicar)

        self.aplicado = self._estado_atual()
        self._atualizar_previa()
        self.mostrar_bateria_salva()
        self.atualizar_conexao()
        GLib.timeout_add_seconds(2, self.atualizar_conexao)

    # =====================================================================
    # Montagem das abas
    # =====================================================================

    def _aba_iluminacao(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        # --- roda de cores + campo hexadecimal + amostras ---
        linha = Gtk.Box(spacing=28)
        self.roda = dica(RodaDeCores(210, ao_mudar=self._roda_mudou),
                         "Roda de cores: clique ou arraste. Ângulo = matiz, distância do centro = saturação. "
                         "Na borda as cores são 100% saturadas (as mais fortes no LED); "
                         "perto do centro ficam esbranquiçadas.")
        linha.append(self.roda)

        coluna = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        coluna.append(rotulo("COR", "secao"))
        campo = Gtk.Box(spacing=10)
        self.previa = dica(PreviaCor(), "A cor escolhida, como aparece na tela.")
        campo.append(self.previa)
        self.campo_hex = dica(Gtk.Entry(max_length=7, width_chars=9, css_classes=["mono"]),
                              "Cor em hexadecimal (#RRGGBB). Digite e a roda acompanha. "
                              "Dica: cores com os três canais acesos (pastel) ficam esbranquiçadas no LED.")
        self.campo_hex.connect("changed", self._hex_mudou)
        campo.append(self.campo_hex)
        coluna.append(campo)

        coluna.append(rotulo("AMOSTRAS (CORES SATURADAS)", "secao", margin_top=6))
        grade = Gtk.Grid(column_spacing=8, row_spacing=8)
        for i, (nome, rgb) in enumerate(AMOSTRAS):
            grade.attach(self._amostra(nome, rgb, self._escolher_cor), i % 4, i // 4, 1, 1)
        coluna.append(grade)

        vivas = Gtk.Box(spacing=12, margin_top=6)
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        textos.append(rotulo("Cores vivas"))
        self.rotulo_enviado = rotulo("", "dim", "mono")
        textos.append(self.rotulo_enviado)
        vivas.append(textos)
        self.vivas = dica(
            Gtk.Switch(active=True, valign=Gtk.Align.CENTER),
            "Cores vivas (ligado = recomendado): aplica uma correção de gama 2,2 (tipo sRGB) antes de enviar. "
            "O LED do mouse é linear, então um canal a 50% na tela acende bem mais claro no LED e as cores "
            "pastel ficam \"lavadas\". Com a correção, #C061CB vai como #891E9A e fica parecido com a tela. "
            "Desligado: manda o valor exato do campo hexadecimal.")
        self.vivas.connect("notify::active", lambda *_a: self._atualizar_previa())
        vivas.append(self.vivas)
        coluna.append(vivas)
        linha.append(coluna)
        caixa.append(linha)

        # --- zonas ---
        caixa.append(rotulo("ZONA", "secao"))
        zonas = Gtk.Box(spacing=8)
        self.botoes_zona = []
        for nome, _numeros, explicacao in ZONAS:
            grupo = self.botoes_zona[0] if self.botoes_zona else None
            botao = dica(Gtk.ToggleButton(label=nome.upper(), group=grupo, css_classes=["contorno"]), explicacao)
            zonas.append(botao)
            self.botoes_zona.append(botao)
        self.botoes_zona[2].set_active(True)
        caixa.append(zonas)

        # --- efeito ---
        caixa.append(rotulo("EFEITO", "secao"))
        efeito = Gtk.Box(spacing=12)
        self.combo_efeito = dica(
            Gtk.DropDown.new_from_strings([e.capitalize() for e in aw720m.EFEITOS]),
            "Efeito do LED: fixo, respirar, transição (usa a 2ª cor), espectro, pulsar ou arco-íris. "
            "Respirar e pulsar passam parte do tempo apagados, por isso parecem mais fracos que o fixo.")
        self.combo_efeito.set_size_request(170, -1)
        self.combo_efeito.connect("notify::selected", lambda *_a: (self._efeito_mudou(), self._atualizar_previa()))
        efeito.append(self.combo_efeito)
        self.rotulo_efeito = rotulo("", "texto-ajuda", wrap=True, hexpand=True)
        efeito.append(self.rotulo_efeito)
        caixa.append(efeito)

        # 2ª cor (só aparece no efeito transição)
        self.linha_cor2 = Gtk.Box(spacing=10)
        self.linha_cor2.append(rotulo("2ª cor", "dim"))
        self.previa2 = dica(PreviaCor(36, 26), "Segunda cor do efeito transição.")
        self.linha_cor2.append(self.previa2)
        self.campo_hex2 = dica(Gtk.Entry(max_length=7, width_chars=9, css_classes=["mono"]),
                               "Segunda cor do efeito transição, em hexadecimal (#RRGGBB). "
                               "A correção \"Cores vivas\" também vale para ela.")
        self.campo_hex2.connect("changed", self._hex2_mudou)
        self.linha_cor2.append(self.campo_hex2)
        for nome, rgb in AMOSTRAS:
            mini = self._amostra(nome, rgb, self._escolher_cor2)
            mini.set_size_request(24, 24)
            self.linha_cor2.append(mini)
        caixa.append(self.linha_cor2)

        # --- brilho ---
        caixa.append(rotulo("BRILHO", "secao"))
        brilho = Gtk.Box(spacing=12)
        self.brilho = dica(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1),
                           "Brilho do LED de 0 a 100 (escala do protocolo APIv7). 100 = máximo, e é o padrão. "
                           "Se a cor parecer fraca, deixe em 100 e use uma cor saturada com \"Cores vivas\" ligado.")
        self.brilho.set_value(100)
        self.brilho.set_hexpand(True)
        self.brilho.connect("value-changed", lambda *_a: self._atualizar_previa())
        brilho.append(self.brilho)
        self.rotulo_brilho = rotulo("100", "valor-medio", width_chars=3, xalign=1)
        brilho.append(self.rotulo_brilho)
        caixa.append(brilho)

        self._mostrar_cor(self.rgb)
        self._mostrar_cor2(self.rgb2)
        self._efeito_mudou()
        return self.rolavel(caixa)

    def _amostra(self, nome, rgb, ao_clicar):
        botao = Gtk.Button(css_classes=["amostra", f"amostra-{rgb_para_hex(rgb)[1:].lower()}"])
        dica(botao, f"{nome} {rgb_para_hex(rgb)}: cor 100% saturada, fica forte no LED.")
        botao.connect("clicked", lambda _b: ao_clicar(rgb))
        return botao

    def _aba_bateria(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        linha = Gtk.Box(spacing=32)
        self.anel = dica(AnelBateria(170, 10),
                         "Nível de bateria do último aviso do mouse (ciano: ok; laranja: abaixo de 20%; "
                         "vermelho: abaixo de 10%).")
        linha.append(self.anel)
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        textos.append(rotulo("BATERIA", "secao"))
        self.rotulo_nivel = rotulo("—", "valor-grande")
        textos.append(self.rotulo_nivel)
        self.rotulo_carga = rotulo("aguardando aviso do mouse", "ciano")
        textos.append(self.rotulo_carga)
        self.rotulo_quando = rotulo("", "dim")
        textos.append(self.rotulo_quando)
        self.rotulo_bruto = dica(rotulo("", "dim", "mono", selectable=True),
                                 "Quadro bruto do último aviso de energia (c0 0a ...), para conferência.")
        textos.append(self.rotulo_bruto)
        linha.append(textos)
        caixa.append(linha)

        caixa.append(rotulo("COMO FUNCIONA", "secao"))
        caixa.append(rotulo(
            "O AW720M não responde quando o painel pergunta a bateria: ele só manda um aviso sozinho "
            "(c0 0a ...) quando você encosta ou tira o carregador magnético. Por isso o valor mostrado é "
            "o do último aviso e pode estar desatualizado. Para atualizar, encoste e tire o carregador.\n\n"
            "O painel fica escutando o tempo todo, mesmo em outras páginas, e guarda o último aviso em "
            "logs/bateria.json. Ainda a confirmar: se o byte 5 do aviso é mesmo a porcentagem "
            "(vale ver se ele sobe durante a carga).", "texto-ajuda", wrap=True))
        return self.rolavel(caixa)

    def _aba_diagnostico(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)
        caixa.append(rotulo("CONEXÃO", "secao"))
        self.rotulo_conexao = rotulo("procurando...", "mono", "dim", selectable=True, wrap=True)
        caixa.append(self.rotulo_conexao)

        caixa.append(rotulo("FERRAMENTAS", "secao", margin_top=6))
        botoes = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=8,
                             max_children_per_line=4, homogeneous=False)
        self.botao_status = self._botao_ferramenta(
            botoes, "Ler status", self.ler_status,
            "Envia o pedido de status (40 03 01 00 01) e mostra a resposta no log. Não muda nada no mouse; "
            "hoje a resposta conhecida é só o OK (ec ac).")
        self.botao_escutar = self._botao_ferramenta(
            botoes, "Escutar 10 s", self.escutar,
            "Só escuta a interface de fabricante por 10 s (não envia nada). Mexa no mouse, aperte o DPI ou "
            "encoste o carregador para ver o que ele manda sozinho.")
        self.botao_extras = self._botao_ferramenta(
            botoes, "Bytes do mouse 10 s", self.escutar_extras,
            "Lê a interface de movimento por 10 s e conta os 5 bytes extras de cada relatório. "
            "Só leitura; mexa o mouse enquanto roda.")
        self._botao_ferramenta(
            botoes, "Teste guiado", self.abrir_teste_guiado,
            "Abre um terminal com o teste guiado (sondar.py guiado): ele pede para você clicar, girar a roda, "
            "apertar o DPI e encostar o carregador, e grava tudo em logs/. Só leitura.")
        caixa.append(botoes)

        caixa.append(rotulo("LOG", "secao", margin_top=6))
        self.log = dica(Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.CHAR,
                                     top_margin=8, bottom_margin=8, left_margin=10, right_margin=10),
                        "Log do painel (também salvo em logs/painel-AAAAMMDD.txt).")
        caixa.append(Gtk.ScrolledWindow(child=self.log, vexpand=True, css_classes=["log"]))
        return caixa

    @staticmethod
    def _botao_ferramenta(caixa, texto, ao_clicar, explicacao):
        botao = dica(Gtk.Button(label=texto.upper(), css_classes=["contorno"]), explicacao)
        botao.connect("clicked", lambda _b: ao_clicar())
        caixa.append(botao)
        return botao

    # =====================================================================
    # Cor: roda, campo hexadecimal, amostras, prévia
    # =====================================================================

    def _mostrar_cor(self, rgb, mover_roda=True):
        """Atualiza tudo que mostra a cor principal (sem gerar eventos em cadeia)."""
        self.rgb = tuple(rgb)
        self.atualizando = True
        self.campo_hex.set_text(rgb_para_hex(self.rgb))
        self.atualizando = False
        self.previa.definir(self.rgb)
        if mover_roda:
            self.roda.definir_rgb(self.rgb)
        self._atualizar_previa()

    def _mostrar_cor2(self, rgb):
        self.rgb2 = tuple(rgb)
        self.atualizando = True
        self.campo_hex2.set_text(rgb_para_hex(self.rgb2))
        self.atualizando = False
        self.previa2.definir(self.rgb2)
        self._atualizar_previa()

    def _roda_mudou(self, r, g, b):
        self._mostrar_cor((r, g, b), mover_roda=False)

    def _escolher_cor(self, rgb):
        self._mostrar_cor(rgb)

    def _escolher_cor2(self, rgb):
        self._mostrar_cor2(rgb)

    def _hex_mudou(self, campo):
        rgb = hex_para_rgb(campo.get_text())
        if self.atualizando or rgb is None:
            return
        self.rgb = rgb
        self.previa.definir(rgb)
        self.roda.definir_rgb(rgb)
        self._atualizar_previa()

    def _hex2_mudou(self, campo):
        rgb = hex_para_rgb(campo.get_text())
        if self.atualizando or rgb is None:
            return
        self.rgb2 = rgb
        self.previa2.definir(rgb)
        self._atualizar_previa()

    def _efeito_mudou(self):
        efeito = self._efeito()
        self.rotulo_efeito.set_text(EFEITOS_DESCRICAO[efeito])
        self.linha_cor2.set_visible(efeito == "transição")

    def _efeito(self):
        return list(aw720m.EFEITOS)[self.combo_efeito.get_selected()]

    def _cores_enviadas(self):
        """As cores que vão de fato ao mouse (com ou sem a correção 'Cores vivas')."""
        if self.vivas.get_active():
            return aw720m.corrigir_cor(*self.rgb), aw720m.corrigir_cor(*self.rgb2)
        return self.rgb, self.rgb2

    def _atualizar_previa(self):
        """Pré-visualização (3D ou SVG) na hora, sem enviar nada: aproxima o que o LED vai mostrar."""
        if not hasattr(self, "rotulo_brilho"):
            return  # ainda montando a tela
        brilho = int(self.brilho.get_value())
        self.rotulo_brilho.set_text(str(brilho))
        enviada, _ = self._cores_enviadas()
        self.rotulo_enviado.set_text(f"vai ao LED como {rgb_para_hex(enviada)}")
        # Com a correção, o LED fica parecido com a tela; sem ela, fica mais claro ("lavado")
        aparente = self.rgb if self.vivas.get_active() else cor_lavada(self.rgb)
        if self.visualizador:
            segunda = self.rgb2 if self.vivas.get_active() else cor_lavada(self.rgb2)
            self.visualizador.set_effect(self._efeito(), rgb_para_hex(aparente), rgb_para_hex(segunda), 50)
            self.visualizador.set_brightness(brilho)
        else:
            self.ilustracao.definir_brilho(aparente, brilho / 100)

    def ao_clicar_zona(self, zona):
        """Clique no logo do 3D: abre a Iluminação com a zona do logo escolhida (a única zona RGB do AW720M)."""
        self.abas.mostrar("iluminacao")
        self.botoes_zona[2].set_active(True)  # "Ambas": o logo da palma ainda não tem zona confirmada
        self.botoes_zona[2].grab_focus()
        self.escrever_log(f"3D: zona '{zona}' escolhida (logo da palma → zonas 0 e 1). Escolha a cor e clique em APLICAR.")

    # =====================================================================
    # Aplicar / cancelar
    # =====================================================================

    def _zona_escolhida(self):
        return next(i for i, b in enumerate(self.botoes_zona) if b.get_active())

    def _estado_atual(self):
        return {"rgb": self.rgb, "rgb2": self.rgb2, "zona": self._zona_escolhida(),
                "efeito": self.combo_efeito.get_selected(), "brilho": self.brilho.get_value(),
                "vivas": self.vivas.get_active()}

    def cancelar(self):
        estado = self.aplicado
        self.botoes_zona[estado["zona"]].set_active(True)
        self.combo_efeito.set_selected(estado["efeito"])
        self.brilho.set_value(estado["brilho"])
        self.vivas.set_active(estado["vivas"])
        self._mostrar_cor(estado["rgb"])
        self._mostrar_cor2(estado["rgb2"])
        self.escrever_log("Controles voltaram para a última configuração aplicada.")

    def aplicar(self):
        if self.mouse is None:
            self.escrever_log("Mouse não conectado: nada enviado.")
            return
        (r, g, b), (r2, g2, b2) = self._cores_enviadas()
        efeito = self._efeito()
        brilho = int(self.brilho.get_value())
        zonas = ZONAS[self._zona_escolhida()][1]
        try:
            for zona in zonas:
                self.escrever_log(f"cor {rgb_para_hex(self.rgb)} -> enviada {rgb_para_hex((r, g, b))}"
                                  f"{' (cores vivas)' if self.vivas.get_active() else ''}, zona {zona}, "
                                  f"efeito {efeito}, brilho {brilho}")
                self.mostrar_respostas(self.mouse.definir_cor(r, g, b, zona=zona, brilho=brilho, efeito=efeito,
                                                              r2=r2, g2=g2, b2=b2))
            self.aplicado = self._estado_atual()
        except OSError as erro:
            self.erro_dispositivo(erro)

    # =====================================================================
    # Conexão e bateria
    # =====================================================================

    def atualizar_conexao(self):
        if self.ocupado:
            return True
        info = aw720m.achar()
        if info is None:
            if self.mouse:
                self.mouse.fechar()
                self.escrever_log("Mouse desconectado.")
            self.mouse, self.info, self.sem_permissao = None, None, False
            self.aviso.set_revealed(False)
            self._mostrar_conexao()
            return True

        if self.mouse is None or info["caminho"] != self.info["caminho"]:
            self.info = info
            try:
                self.mouse = aw720m.Mouse(info["caminho"])
                self.sem_permissao = False
                self.escrever_log(f"Conectado pelo {info['modo']} ({info['caminho']}).")
                self.iniciar_ouvinte(info["caminho"])
            except aw720m.SemPermissao:
                self.mouse = None
                self.sem_permissao = True
            self.aviso.set_revealed(self.sem_permissao)
        self._mostrar_conexao()
        return True  # mantém o timer

    def modo_legivel(self):
        """'Dongle 2.4G' / 'Cabo USB-C' ou None se o mouse não estiver ligado."""
        if self.info is None:
            return None
        return {0x3029: "Dongle 2.4G", 0x3028: "Cabo USB-C"}.get(self.info["pid"], self.info["modo"])

    def _mostrar_conexao(self):
        modo = self.modo_legivel()
        if modo is None:
            self.definir_status("Mouse não encontrado: ligue o mouse e conecte o dongle ou o cabo.", False)
            self.rotulo_conexao.set_text("não encontrado")
        elif self.sem_permissao:
            self.definir_status(f"{modo} encontrado, mas sem permissão para abrir {self.info['caminho']}.", False)
            self.rotulo_conexao.set_text(f"{modo} · 413c:{self.info['pid']:04x} · {self.info['caminho']} (sem permissão)")
        else:
            self.definir_status(f"Conectado pelo {modo} · {self.info['caminho']}", True)
            self.rotulo_conexao.set_text(
                f"{modo} · 413c:{self.info['pid']:04x} · comandos {self.info['caminho']} · "
                f"movimento {self.info.get('caminho_mouse', '?')}")
        ligado = self.mouse is not None and not self.ocupado
        for botao in (self.botao_aplicar, self.botao_status, self.botao_escutar, self.botao_extras):
            botao.set_sensitive(ligado)
        self._mostrar_cabecalho()

    def _mostrar_cabecalho(self):
        """'BATERIA ▮ 20%' acima da ilustração."""
        if self.bateria:
            nivel = self.bateria["bateria"]
            cor = "#00c8d7" if nivel >= 20 else "#ffb020" if nivel >= 10 else "#f24d4d"
            self.cabecalho.set_markup(f'BATERIA  <span foreground="{cor}">▮</span> '
                                      f'<span foreground="#ffffff">{nivel}%</span>')
            estado = "carregando" if self.bateria["carregando"] else "na bateria"
            detalhe = f"{estado} · aviso de {self.bateria['quando']}"
        else:
            self.cabecalho.set_markup('BATERIA  <span foreground="#5d636b">▮</span> —')
            detalhe = "aguardando aviso (encoste ou tire o carregador)"
        modo = self.modo_legivel()
        self.subcabecalho.set_text(f"{modo} · {detalhe}" if modo else f"desconectado · {detalhe}")

    def iniciar_ouvinte(self, caminho):
        """Abre uma segunda leitura da interface de fabricante só para esperar os avisos c0 0a."""
        if self.ouvinte and self.ouvinte.is_alive():
            return

        def rodar():
            try:
                fd = os.open(caminho, os.O_RDONLY)
            except OSError:
                return
            try:
                while True:
                    energia = aw720m.ler_energia(os.read(fd, aw720m.TAMANHO))
                    if energia:
                        GLib.idle_add(self.atualizar_bateria, energia)
            except OSError:
                pass  # mouse desconectado; o timer abre de novo quando ele voltar
            os.close(fd)

        self.ouvinte = threading.Thread(target=rodar, daemon=True)
        self.ouvinte.start()

    def mostrar_bateria(self, nivel, carregando, quando, bruto=""):
        self.bateria = {"bateria": nivel, "carregando": carregando, "quando": quando}
        self.anel.definir(nivel, carregando)
        self.rotulo_nivel.set_text(f"{nivel}%")
        self.rotulo_carga.set_text("Carregando (carregador encostado)" if carregando else "Na bateria")
        self.rotulo_quando.set_text(f"Último aviso: {quando}")
        self.rotulo_bruto.set_text(bruto)
        self._mostrar_cabecalho()

    def atualizar_bateria(self, energia):
        quando = time.strftime("%d/%m %H:%M")
        self.mostrar_bateria(energia["bateria"], energia["carregando"], quando, energia["bruto"])
        self.escrever_log(f"aviso de energia: {energia['bruto']}")
        dados = {"bateria": energia["bateria"], "carregando": energia["carregando"], "quando": quando}
        os.makedirs(os.path.dirname(ARQUIVO_BATERIA), exist_ok=True)
        with open(ARQUIVO_BATERIA, "w") as f:
            json.dump(dados, f)
        return False

    def mostrar_bateria_salva(self):
        if os.path.exists(ARQUIVO_BATERIA):
            with open(ARQUIVO_BATERIA) as f:
                dados = json.load(f)
            self.mostrar_bateria(dados["bateria"], dados["carregando"], dados["quando"])

    # =====================================================================
    # Diagnóstico
    # =====================================================================

    def escrever_log(self, texto):
        linha = f"[{time.strftime('%H:%M:%S')}] {texto}\n"
        buffer = self.log.get_buffer()
        buffer.insert(buffer.get_end_iter(), linha)
        # Também guarda em logs/painel-AAAAMMDD.txt para analisar depois
        os.makedirs(os.path.join(PASTA, "logs"), exist_ok=True)
        with open(os.path.join(PASTA, "logs", f"painel-{time.strftime('%Y%m%d')}.txt"), "a") as f:
            f.write(linha)
        self.log.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 0)
        return False  # para o GLib.idle_add não repetir

    def mostrar_respostas(self, respostas):
        if not respostas:
            self.escrever_log("resposta: nenhuma")
        for resposta in respostas:
            self.escrever_log(f"resposta: {aw720m.hexa(resposta)}")
            energia = aw720m.ler_energia(resposta)
            if energia:
                self.atualizar_bateria(energia)

    def erro_dispositivo(self, erro):
        self.escrever_log(f"Erro: {erro}")
        self.mouse = None  # o timer tenta abrir de novo
        return False

    def dar_permissao(self):
        self.escrever_log("Pedindo a senha para instalar a regra udev...")

        def rodar():
            resultado = subprocess.run(["pkexec", SCRIPT_PERMISSAO], capture_output=True, text=True)
            saida = (resultado.stdout + resultado.stderr).strip()
            GLib.idle_add(self.escrever_log, saida or f"pkexec terminou com código {resultado.returncode}")

        threading.Thread(target=rodar, daemon=True).start()

    def ler_status(self):
        self.escrever_log(f"enviado: {aw720m.hexa(aw720m.CMD_STATUS)}")
        try:
            self.mostrar_respostas(self.mouse.status())
        except OSError as erro:
            self.erro_dispositivo(erro)

    def _comecar_escuta(self, aviso):
        self.ocupado = True
        self._mostrar_conexao()
        self.abas.mostrar("diagnostico")
        self.escrever_log(aviso)

    def escutar(self):
        self._comecar_escuta("Escutando 10 s (mexa no mouse, aperte o DPI, encoste o carregador)...")
        mouse = self.mouse

        def rodar():
            try:
                quadros = mouse.escutar(10)
                inicio = quadros[0][0] if quadros else 0
                for t, quadro in quadros:
                    GLib.idle_add(self.escrever_log, f"+{t - inicio:5.2f}s {aw720m.hexa(quadro)}")
                GLib.idle_add(self.escrever_log, f"Fim da escuta: {len(quadros)} quadro(s).")
            except OSError as erro:
                GLib.idle_add(self.erro_dispositivo, erro)
            GLib.idle_add(self.fim_escuta)

        threading.Thread(target=rodar, daemon=True).start()

    def escutar_extras(self):
        caminho = self.info.get("caminho_mouse")
        if not caminho:
            self.escrever_log("Interface de movimento não encontrada.")
            return
        self._comecar_escuta("Mexa o mouse por 10 s (lendo os 5 bytes extras de cada movimento)...")

        def rodar():
            try:
                contagem = aw720m.escutar_extras_do_mouse(caminho, 10)
                for extras, n in contagem.items():
                    GLib.idle_add(self.escrever_log, f"{n:5d}x  {' '.join(f'{b:02x}' for b in extras)}")
                if not contagem:
                    GLib.idle_add(self.escrever_log, "Nenhum movimento recebido.")
            except (OSError, aw720m.SemPermissao) as erro:
                GLib.idle_add(self.escrever_log, f"Erro: {erro}")
            GLib.idle_add(self.fim_escuta)

        threading.Thread(target=rodar, daemon=True).start()

    def fim_escuta(self):
        self.ocupado = False
        self._mostrar_conexao()
        return False

    def abrir_teste_guiado(self):
        try:
            subprocess.Popen(["gnome-terminal", "--", TESTE_GUIADO])
            self.escrever_log("Teste guiado aberto num terminal novo.")
        except OSError as erro:
            self.escrever_log(f"Não consegui abrir o gnome-terminal: {erro}")
