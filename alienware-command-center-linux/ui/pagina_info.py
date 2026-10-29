"""Página "Somente informações": para aparelhos USB que o painel não sabe configurar."""

from gi.repository import Gtk

from ui.pagina_base import PaginaDispositivo
from ui.widgets import grade_info, rotulo, titulo

# Nomes das classes de interface USB mais comuns
CLASSES = {"01": "áudio", "02": "comunicação", "03": "HID (teclado/mouse)", "08": "armazenamento",
           "0a": "dados", "0e": "vídeo", "e0": "sem fio", "ef": "diversos", "ff": "do fabricante"}
PROTOCOLOS_HID = {"01": "teclado", "02": "mouse"}


class PaginaInfo(PaginaDispositivo):
    def __init__(self, janela):
        super().__init__(janela, "INFO", "Dispositivo", "usb.svg")
        self.caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.abas.adicionar("informacoes", "Informações", self.rolavel(self.caixa),
                            "Dados lidos do sysfs (/sys/bus/usb/devices). O painel não envia nada a este aparelho.")
        self.status.set_text("Somente informações: o painel não configura este aparelho.")

    def mostrar(self, d):
        """Preenche a página com o dicionário de dispositivos.listar_usb()."""
        novo = titulo("INFO", d["nome"])
        self.titulo.set_markup(novo.get_label())
        self.ilustracao.trocar_arquivo("teclado.svg" if d["tipo"] == "teclado" else "usb.svg")
        self.cabecalho.set_markup('<span foreground="#8a9099">SOMENTE INFORMAÇÕES</span>')
        self.subcabecalho.set_text(f"{d['tipo_texto']} · porta {d['porta']}")
        while (filho := self.caixa.get_first_child()):
            self.caixa.remove(filho)
        interfaces = []
        for i, (classe, protocolo, driver) in enumerate(d["interfaces"]):
            nome = CLASSES.get(classe, f"classe {classe}")
            if classe == "03" and protocolo in PROTOCOLOS_HID:
                nome = f"HID {PROTOCOLOS_HID[protocolo]}"
            interfaces.append(f"{i}: {nome} · driver {driver}")
        self.caixa.append(grade_info([
            ("Nome", d["produto"]),
            ("Tipo", d["tipo_texto"]),
            ("Fabricante", d["fabricante"]),
            ("ID", d["id"]),
            ("Velocidade", d["velocidade"]),
            ("Porta", d["porta"]),
            ("Versão", d["versao"]),
            ("Interfaces", "\n".join(interfaces) or "—"),
        ]))
        self.caixa.append(rotulo(
            "O painel configura o Alienware AW720M (mouse) e o AW725H (headset) e tem prévia do Redragon K617 "
            "Fizz Rainbow (teclado). Para este aparelho ele mostra apenas o que o Linux informa.", "texto-ajuda", wrap=True))
        self.status.set_text(f"Somente informações · {d['nome']} ({d['id']}) na porta {d['porta']}")
