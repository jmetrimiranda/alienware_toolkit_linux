"""Molde das páginas de aparelho, no estilo da tela de dispositivo do AWCC:

  ‹  TÍTULO │ SUBTÍTULO
  ┌──────────────────────┐ ┌────────────────────────────┐
  │ BATERIA ▮ 20%        │ │ ABA 1   ABA 2   ABA 3      │
  │                      │ │                            │
  │  3D (ou SVG reserva) │ │   ajustes da aba           │
  │                      │ │                            │
  └──────────────────────┘ └────────────────────────────┘
  status ................................ ✕ CANCELAR  ✓ APLICAR
"""

import os

from gi.repository import Gdk, GLib, Gtk

import aparencia
from ui.widgets import Abas, Ilustracao, dica, rotulo, titulo


def tem_3d():
    """O 3D precisa de WebGL numa tela de verdade: no broadway (capturas de teste) ou com
    ALIENWARE_SEM_3D=1 a página usa a ilustração SVG."""
    if os.environ.get("ALIENWARE_SEM_3D") == "1":
        return False
    return "Broadway" not in type(Gdk.Display.get_default()).__name__


class PaginaDispositivo(Gtk.Box):
    def __init__(self, janela, primeira, segunda, arquivo_svg, luz=None, camada_luz=None, modelo3d=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.janela = janela
        self.modelo3d = modelo3d
        self.visualizador = None  # Visualizador3D (ou None quando a página usa só o SVG)
        self.ilustracao = None    # Ilustracao SVG (ou None quando o 3D está na tela)

        # --- linha do título, com o botão de voltar ao Início ---
        topo = Gtk.Box(spacing=8, margin_start=18, margin_end=28, margin_top=4, margin_bottom=14)
        voltar = dica(Gtk.Button(icon_name="go-previous-symbolic", css_classes=["voltar"]),
                      "Voltar para o Início (lista de dispositivos USB)")
        voltar.connect("clicked", lambda _b: janela.abrir("inicio"))
        topo.append(voltar)
        self.titulo = titulo(primeira, segunda)
        topo.append(self.titulo)
        self.append(topo)

        # Lugar para avisos (ex.: falta de permissão) logo abaixo do título
        self.avisos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.append(self.avisos)

        # --- corpo: ilustração à esquerda, painel com abas à direita ---
        corpo = Gtk.Box(spacing=24, vexpand=True, margin_start=28, margin_end=28, margin_bottom=20)
        esquerda = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, width_request=360, hexpand=True)
        self.cabecalho = Gtk.Label(use_markup=True, xalign=0, css_classes=["secao"])
        esquerda.append(self.cabecalho)
        self.subcabecalho = rotulo("", "dim")
        esquerda.append(self.subcabecalho)
        if modelo3d and tem_3d():
            esquerda.append(self._montar_3d(modelo3d))
        else:
            self.ilustracao = Ilustracao(arquivo_svg, luz=luz, camada_luz=camada_luz)
            esquerda.append(self.ilustracao)
        corpo.append(esquerda)

        painel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["painel"], width_request=600)
        self.abas = Abas()
        painel.append(self.abas)
        corpo.append(painel)
        self.append(corpo)

        # --- barra inferior ---
        barra = Gtk.Box(spacing=10, css_classes=["barra-inferior"])
        self.status = rotulo("", "dim", hexpand=True, ellipsize=3)  # 3 = Pango.EllipsizeMode.END
        barra.append(self.status)
        self.botoes_barra = Gtk.Box(spacing=6)
        barra.append(self.botoes_barra)
        self.append(barra)

    # ---------- visualizador 3D ----------

    def _montar_3d(self, modelo):
        """Visualizador 3D com dois botões discretos no canto: girar sozinho e voltar à vista inicial."""
        from ui.visualizador3d import Visualizador3D  # importa o WebKit só quando precisa
        self.visualizador = Visualizador3D(modelo, ao_clicar_zona=self.ao_clicar_zona)
        self.visualizador.set_body_color(aparencia.cor_hex(modelo))
        aparencia.ouvintes.append(self._cor_do_corpo_mudou)

        botoes = Gtk.Box(spacing=4, halign=Gtk.Align.END, valign=Gtk.Align.END, margin_end=8, margin_bottom=8)
        self.botao_girar = dica(Gtk.ToggleButton(icon_name="object-rotate-right-symbolic", active=True,
                                                 css_classes=["botao-3d"]),
                                "Girar sozinho: liga ou desliga o giro automático do modelo 3D. "
                                "Arrastar com o mouse gira de qualquer jeito.")
        self.botao_girar.connect("toggled", lambda b: self.visualizador.auto_rotate(b.get_active()))
        botoes.append(self.botao_girar)
        resetar = dica(Gtk.Button(icon_name="zoom-fit-best-symbolic", css_classes=["botao-3d"]),
                       "Resetar vista: volta o modelo 3D para o ângulo e o zoom iniciais (o mesmo que o duplo clique).")
        resetar.connect("clicked", lambda _b: self.visualizador.reset_view())
        botoes.append(resetar)

        sobreposicao = Gtk.Overlay(child=self.visualizador, hexpand=True, vexpand=True)
        sobreposicao.add_overlay(botoes)
        return sobreposicao

    def _cor_do_corpo_mudou(self, aparelho, cor):
        if aparelho == self.modelo3d and self.visualizador:
            self.visualizador.set_body_color(cor)

    def ao_clicar_zona(self, zona):
        """Clique numa zona de luz do 3D ('logo', 'logo_esq', 'tecla:Esc'...). As filhas sobrescrevem."""

    def ao_esconder(self):
        """Chamado pela janela quando a página sai da tela: para o giro automático (economiza GPU)."""
        if self.visualizador:
            self.visualizador.auto_rotate(False)

    def _voltar_giro(self):
        if self.visualizador:
            self.visualizador.auto_rotate(self.botao_girar.get_active())

    # ---------- utilidades para as páginas filhas ----------

    def botao_barra(self, texto, classe, explicacao, ao_clicar):
        """Adiciona um botão na barra inferior ('cancelar' = texto, 'aplicar' = ciano cheio)."""
        botao = dica(Gtk.Button(label=texto, css_classes=[classe]), explicacao)
        botao.connect("clicked", lambda _b: ao_clicar())
        self.botoes_barra.append(botao)
        return botao

    def definir_status(self, texto, ok):
        """Texto da barra inferior com uma bolinha ciano (ok) ou laranja (problema)."""
        cor = "#00c8d7" if ok else "#ffb020"
        self.status.set_markup(f'<span foreground="{cor}">●</span>  {GLib.markup_escape_text(texto)}')

    @staticmethod
    def rolavel(conteudo):
        """Coloca o conteúdo de uma aba numa área com rolagem e margens."""
        conteudo.set_margin_top(20)
        conteudo.set_margin_bottom(20)
        conteudo.set_margin_start(24)
        conteudo.set_margin_end(24)
        return Gtk.ScrolledWindow(child=conteudo, hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)

    def ao_mostrar(self):
        """Chamado pela janela quando a página aparece (as filhas podem reler dados aqui)."""
        self._voltar_giro()
