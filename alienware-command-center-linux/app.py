"""Alienware Toolkit for Linux: painel GTK4 no estilo do Alienware Command Center.

Entrada do programa: carrega o tema (estilo.css, escuro forçado) e abre a janela de ui/janela.py.

Modo de captura (testes sem mexer na tela): com as variáveis
  ALIENWARE_CAPTURA=/caminho/arquivo.png
  ALIENWARE_PAGINA=inicio | mouse | mouse:bateria | headset | headset:eq | teclado:atalhos | config | outro | ...
o app abre a página, espera ~2 s, salva a janela em PNG e fecha. Nada é enviado ao mouse nesse modo.

Modo de demonstração (vídeos do README): ALIENWARE_DEMO=<roteiro> (veja demo.py). O app navega sozinho,
grava quadros da janela em ALIENWARE_DEMO_PASTA e fecha. Só pré-visualiza: nada vai aos aparelhos.
"""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)  # para achar aw720m.py, dispositivos.py e a pasta ui/ de qualquer lugar
APP_ID = "io.github.jmetrimiranda.AlienwareToolkit"  # igual ao .desktop (desktop/) e à dock
# Ícones do app no repositório (antes de rodar o desktop/install-desktop.sh)
ICONES_REPO = os.path.join(os.path.dirname(PASTA), "desktop", "icons")

from ui.janela import Janela  # noqa: E402


def carregar_tema():
    """Tema escuro forçado + CSS próprio + pasta assets/ como fonte de ícones (logo da janela)."""
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    tela = Gdk.Display.get_default()
    provedor = Gtk.CssProvider()
    provedor.connect("parsing-error", lambda _p, secao, erro: print(f"estilo.css: {secao.to_string()}: {erro.message}"))
    provedor.load_from_path(os.path.join(PASTA, "estilo.css"))
    Gtk.StyleContext.add_provider_for_display(tela, provedor, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    tema = Gtk.IconTheme.get_for_display(tela)
    tema.add_search_path(os.path.join(PASTA, "assets"))
    if os.path.isdir(ICONES_REPO):
        tema.add_search_path(ICONES_REPO)  # desktop/icons/hicolor/... (ícone novo com headset)
    Gtk.Window.set_default_icon_name(APP_ID)


def capturar(janela, arquivo):
    """Renderiza a janela inteira num PNG (sem tirar print da tela)."""
    largura, altura = janela.get_width(), janela.get_height()
    desenho = Gtk.WidgetPaintable.new(janela)
    snapshot = Gtk.Snapshot.new()
    desenho.snapshot(snapshot, largura, altura)
    textura = janela.get_renderer().render_texture(snapshot.to_node(), None)
    textura.save_to_png(arquivo)
    print(f"captura salva em {arquivo} ({largura}x{altura})")


def preparar_captura(app, janela):
    arquivo = os.environ["ALIENWARE_CAPTURA"]
    # Sem navegador ligado ao broadway o relógio de quadros não anda, e as transições ficariam paradas
    Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
    pagina, _, aba = os.environ.get("ALIENWARE_PAGINA", "inicio").replace("_", ":").partition(":")
    if pagina == "outro":
        # primeiro aparelho não suportado (de preferência um teclado)
        import dispositivos
        outros = [d for d in dispositivos.listar_usb() if not d["suportado"]]
        outros.sort(key=lambda d: d["tipo"] != "teclado")
        if outros:
            janela.abrir_dispositivo(outros[0])
    elif pagina in ("mouse", "headset", "teclado"):
        janela.abrir_dispositivo({"tipo": pagina, "suportado": True})
    else:
        janela.abrir(pagina)
    if aba:
        janela.pilha.get_visible_child().abas.mostrar(aba)

    def terminar():
        capturar(janela, arquivo)
        app.quit()
        return False

    # ALIENWARE_ESPERA = segundos até a captura (padrão 2,5; o log do kernel do headset leva ~4 s)
    GLib.timeout_add(int(float(os.environ.get("ALIENWARE_ESPERA", "2.5")) * 1000), terminar)


def main():
    captura = "ALIENWARE_CAPTURA" in os.environ
    demo = os.environ.get("ALIENWARE_DEMO")
    # NON_UNIQUE na captura/demo: não conversa com um painel que já esteja aberto na sessão
    flags = Gio.ApplicationFlags.NON_UNIQUE if (captura or demo) else Gio.ApplicationFlags.DEFAULT_FLAGS
    app = Adw.Application(application_id=APP_ID, flags=flags)

    def ativar(app):
        if app.get_active_window():  # segunda abertura: só traz a janela para a frente
            app.get_active_window().present()
            return
        carregar_tema()
        janela = Janela(app)
        janela.present()
        if captura:
            preparar_captura(app, janela)
        elif demo:
            import demo as roteiro
            roteiro.iniciar(app, janela, demo)

    app.connect("activate", ativar)
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
