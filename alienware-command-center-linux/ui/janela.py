"""Janela principal: barra lateral só com ícones + páginas (Início, dispositivo, Configurações, Sobre)."""

from gi.repository import Adw, Gtk

from ui.pagina_config import PaginaConfig, PaginaSobre
from ui.pagina_headset import PaginaHeadset
from ui.pagina_info import PaginaInfo
from ui.pagina_inicio import PaginaInicio
from ui.pagina_mouse import PaginaMouse
from ui.pagina_teclado import PaginaTeclado
from ui.widgets import Ilustracao, dica

# Página -> item da barra lateral que fica aceso
ITEM_DA_PAGINA = {"inicio": "inicio", "mouse": "dispositivo", "headset": "dispositivo", "teclado": "dispositivo",
                  "info": "dispositivo", "config": "config", "sobre": "sobre"}
ICONE_DO_TIPO = {"mouse": "input-mouse-symbolic", "headset": "audio-headset-symbolic",
                 "teclado": "input-keyboard-symbolic", "usb": "drive-removable-media-symbolic"}


class Janela(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Alienware Toolkit")
        self.set_default_size(1280, 800)
        # ícone do app (desktop/icons; a pasta entra no tema de ícones em app.py)
        self.set_icon_name("io.github.jmetrimiranda.AlienwareToolkit")
        self.ultimo_dispositivo = "mouse"
        self.pagina_atual = None

        raiz = Gtk.Box()

        # --- barra lateral ---
        lateral = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["lateral"])
        logo = dica(Ilustracao("logo.svg", 38, 44), "Alienware Toolkit for Linux (painel no estilo do Command Center)")
        logo.set_hexpand(False)
        logo.set_vexpand(False)
        logo.add_css_class("logo")
        lateral.append(logo)
        self.itens = {}
        self._item(lateral, "inicio", "go-home-symbolic", "Início: aparelhos USB conectados (cartões)")
        self._item(lateral, "dispositivo", "input-mouse-symbolic",
                   "Dispositivo: volta para o último aparelho aberto (no começo, o mouse AW720M)")
        lateral.append(Gtk.Box(vexpand=True))
        self._item(lateral, "config", "emblem-system-symbolic",
                   "Configurações: cor dos aparelhos no 3D, permissões (udev) e registros")
        self._item(lateral, "sobre", "help-about-symbolic", "Sobre o painel")
        lateral.append(Gtk.Box(height_request=12))
        raiz.append(lateral)

        # --- área da direita: faixa de cima (arrastar/fechar) + páginas ---
        direita = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        faixa = Gtk.Box(css_classes=["topo"])
        faixa.append(Gtk.Label(label="ALIENWARE TOOLKIT · LINUX", css_classes=["marca"], hexpand=True, xalign=0))
        faixa.append(Gtk.WindowControls(side=Gtk.PackType.END))
        direita.append(dica(Gtk.WindowHandle(child=faixa), "Arraste aqui para mover a janela"))

        self.pilha = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        # O mouse é criado primeiro: ele mantém a conexão e a bateria, que o Início também mostra
        self.pagina_mouse = PaginaMouse(self)
        self.pagina_headset = PaginaHeadset(self)
        self.pagina_teclado = PaginaTeclado(self)
        self.pagina_info = PaginaInfo(self)
        self.pagina_inicio = PaginaInicio(self)
        for nome, pagina in (("inicio", self.pagina_inicio), ("mouse", self.pagina_mouse),
                             ("headset", self.pagina_headset), ("teclado", self.pagina_teclado),
                             ("info", self.pagina_info),
                             ("config", PaginaConfig(self)), ("sobre", PaginaSobre(self))):
            self.pilha.add_named(pagina, nome)
        direita.append(self.pilha)
        raiz.append(direita)

        self.set_content(raiz)
        self.abrir("inicio")

    def _item(self, lateral, nome, icone, explicacao):
        botao = dica(Gtk.Button(icon_name=icone), explicacao)
        botao.connect("clicked", lambda _b: self.abrir(self.ultimo_dispositivo if nome == "dispositivo" else nome))
        lateral.append(botao)
        self.itens[nome] = botao

    def abrir(self, nome):
        """Mostra uma página e acende o item certo da barra lateral."""
        anterior = self.pilha.get_child_by_name(self.pagina_atual) if self.pagina_atual else None
        if anterior is not None and self.pagina_atual != nome and hasattr(anterior, "ao_esconder"):
            anterior.ao_esconder()
        self.pagina_atual = nome
        self.pilha.set_visible_child_name(nome)
        for item, botao in self.itens.items():
            if item == ITEM_DA_PAGINA[nome]:
                botao.add_css_class("ativo")
            else:
                botao.remove_css_class("ativo")
        pagina = self.pilha.get_child_by_name(nome)
        if hasattr(pagina, "ao_mostrar"):
            pagina.ao_mostrar()

    def abrir_dispositivo(self, d):
        """Abre a página certa para um item de dispositivos.listar_usb()."""
        if d["tipo"] in ("mouse", "headset") or (d["tipo"] == "teclado" and d.get("suportado")):
            nome = d["tipo"]
        else:
            self.pagina_info.mostrar(d)
            nome = "info"
        self.ultimo_dispositivo = nome
        self.itens["dispositivo"].set_icon_name(ICONE_DO_TIPO[d["tipo"]])
        self.abrir(nome)
