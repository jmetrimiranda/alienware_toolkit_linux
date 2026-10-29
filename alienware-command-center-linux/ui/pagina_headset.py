"""Página do headset Alienware AW725H: estado, estabilidade do dongle, proteção contra quedas, áudio
e as abas de ui/abas_headset_extras.py (Mic, EQ, Luz, Bateria).

O headset não tem protocolo de configuração conhecido no Linux. O que o painel faz:
- lê porta, velocidade e firmware do dongle no sysfs;
- conta no log do kernel quantas vezes o chip do dongle reiniciou (aparece como 0e8d:0003);
- liga/desliga o protetor (alienware-headset-guard.service, de aw725h-headset-disconnect-fix/) e mostra o estado;
- "Som de um lado só?": testa os canais e reabre o stream com o próprio script do protetor;
- ajusta saída/entrada padrão, volume e mudo pelo PipeWire (wpctl).
Os comandos lentos rodam em segundo plano para a tela não travar.
"""

import os
import subprocess
import sys

from gi.repository import GLib, Gtk

import dispositivos
from ui.pagina_base import PaginaDispositivo
from ui.widgets import BarrasPorHora, dica, em_segundo_plano, grade_info, rotulo

DICA_PROTETOR = ("Reabre o áudio do headset a cada ~110 s com um corte de ~0,5 s, para o dongle (firmware 1.00) "
                 "não reiniciar. Correção definitiva: atualizar o firmware (veja "
                 "aw725h-headset-disconnect-fix/README.md).")
DICA_ATUALIZAR = ("Relê tudo agora: conexão do dongle, reinícios no log do kernel, serviço de proteção, áudio e a aba "
                  "aberta. Não envia nada ao headset (só leitura).")

# O protetor escreve o campo "mode" em inglês
MODOS = {"waiting for audio": "esperando áudio", "headset not connected": "headset desconectado",
         "no audio": "sem áudio", "stopped": "parado"}


def modo_legivel(modo):
    """'playing for 76 s' -> 'tocando há 76 s'; os outros modos pela tabela MODOS."""
    if modo and modo.startswith("playing for "):
        return "tocando há " + modo[len("playing for "):]
    return MODOS.get(modo, modo)


class PaginaHeadset(PaginaDispositivo):
    def __init__(self, janela):
        super().__init__(janela, "AW725H", "Headset", "headset.svg", modelo3d="headset")
        self.atualizando = False  # evita que mudanças feitas pelo código mexam no áudio
        self.nos = {"saida": None, "entrada": None}

        self.abas.adicionar("estado", "Estado", self._aba_estado(),
                            "Conexão do dongle, porta USB, velocidade e versão de firmware.")
        self.abas.adicionar("estabilidade", "Estabilidade", self._aba_estabilidade(),
                            "Quantas vezes o dongle reiniciou sozinho (contado no log do kernel).")
        self.abas.adicionar("protecao", "Proteção", self._aba_protecao(),
                            "Proteção contra quedas: reabre o áudio do headset a cada ~110 s para o dongle não reiniciar.")
        self.abas.adicionar("audio", "Áudio", self._aba_audio(),
                            "Saída e entrada padrão, volume e mudo do headset (PipeWire).")
        self.abas.ao_trocar = self._aba_aberta
        self.lendo_reinicios = False  # o journalctl leva alguns segundos; evita duas leituras ao mesmo tempo
        self.voltas = 0  # conta as voltas do timer de 10 s

        self.botao_atualizar = self.botao_barra("↻  ATUALIZAR", "aplicar", DICA_ATUALIZAR, self.atualizar_tudo)

        # Abas novas: Mic, EQ, Luz e Bateria (ui/abas_headset_extras.py). Elas usam o 3D desta página.
        from ui.abas_headset_extras import adicionar_abas_extras
        self.extras = adicionar_abas_extras(self)
        # O ✕ CANCELAR / ✓ APLICAR do equalizador vão para a barra inferior e só aparecem na aba EQ
        eq = self.extras.abas["equalizador"]
        self.botoes_eq = (eq.cancelar_botao, eq.aplicar_botao)
        for botao in self.botoes_eq:
            botao.get_parent().remove(botao)
            self.botoes_barra.append(botao)
        anterior = self.abas.ao_trocar

        def trocar(nome):
            anterior(nome)
            self._barra_da_aba(nome)
        self.abas.ao_trocar = trocar
        self._barra_da_aba(self.abas.atual())

        self.ler_estado()
        self.ler_reinicios()  # já começa a ler o log do kernel, para estar pronto quando a página abrir
        GLib.timeout_add_seconds(10, self._timer)

    def _barra_da_aba(self, nome):
        """Na aba EQ a barra mostra ↻ ATUALIZAR (contorno) + ✕ CANCELAR + ✓ APLICAR; nas outras, só ATUALIZAR."""
        no_eq = nome == "equalizador"
        for botao in self.botoes_eq:
            botao.set_visible(no_eq)
        self.botao_atualizar.set_css_classes(["contorno"] if no_eq else ["aplicar"])

    # =====================================================================
    # Abas
    # =====================================================================

    def _aba_estado(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.caixa_estado = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caixa.append(self.caixa_estado)
        caixa.append(rotulo("FIRMWARE", "secao", margin_top=8))
        caixa.append(rotulo(
            "Versão mais recente publicada pela Dell em jul/2025 (DSA-2025-303). "
            "A atualização só roda no Windows e grava sempre os dois juntos (headset e dongle). "
            "O Linux só enxerga a versão do dongle (bcdDevice).", "texto-ajuda", wrap=True))
        link = dica(Gtk.LinkButton(uri=dispositivos.URL_FIRMWARE, label="Página do firmware na Dell ↗",
                                   halign=Gtk.Align.START),
                    "Abre no navegador a página de download do firmware do AW725H (driver 3GCWV) no site da Dell.")
        caixa.append(link)
        caixa.append(self._bloco_um_lado())
        caixa.append(rotulo("CONSERTO", "secao", margin_top=8))
        caixa.append(rotulo(
            "Até atualizar o firmware, o protetor (aba Proteção) reabre o áudio a cada 110 s e o dongle não "
            "reinicia. O guia explica o protetor, a regra do ModemManager e o firmware.", "texto-ajuda", wrap=True))
        guia = dica(Gtk.Button(label="ABRIR GUIA", css_classes=["contorno"], halign=Gtk.Align.START),
                    "Abre aw725h-headset-disconnect-fix/README.md (guia do conserto do headset, na pasta do "
                    "repositório ao lado do app) com xdg-open.")
        guia.connect("clicked", lambda _b: self._abrir_guia())
        caixa.append(guia)
        self.rotulo_guia = rotulo("", "dim", wrap=True)
        caixa.append(self.rotulo_guia)
        return self.rolavel(caixa)

    def _bloco_um_lado(self):
        """Seção "Som de um lado só?": testa os canais e reabre o stream (aw725h_guard.py --reopen 1.0)."""
        bloco = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["bloco"], margin_top=8)
        bloco.append(rotulo("SOM DE UM LADO SÓ?", "secao"))
        bloco.append(rotulo(
            "Com o firmware 1.00, o dongle às vezes volta tocando em um lado só depois que o áudio reabre. "
            "O Linux manda os dois canais iguais; o problema é do dongle. Reabrir o áudio com uma pausa de 1 s "
            "(como numa reconexão) costuma resolver. Se não resolver, clique de novo ou desligue e ligue o headset.",
            "texto-ajuda", wrap=True))
        botoes = Gtk.Box(spacing=8)
        self.botao_canais = dica(
            Gtk.Button(label="TESTAR CANAIS (E/D)", css_classes=["contorno"]),
            "Toca \"Front Left\" só no lado esquerdo e depois \"Front Right\" só no direito (pw-play no "
            "headset). Se uma das vozes não sair, o som está preso em um lado. Comando: "
            "python3 aw725h-headset-disconnect-fix/aw725h_guard.py --channel-test")
        self.botao_canais.connect("clicked", lambda _b: self._rodar_guarda(["--channel-test"], "Tocando o teste..."))
        botoes.append(self.botao_canais)
        self.botao_reparar = dica(
            Gtk.Button(label="REPARAR SOM AGORA", css_classes=["contorno"]),
            "Fecha e reabre o áudio do headset com uma pausa de 1 s, sem perder o que está tocando "
            "(os apps vão para uma saída muda e voltam). Comando: "
            "python3 aw725h-headset-disconnect-fix/aw725h_guard.py --reopen 1.0")
        self.botao_reparar.connect("clicked", lambda _b: self._rodar_guarda(["--reopen", "1.0"], "Reabrindo o áudio..."))
        botoes.append(self.botao_reparar)
        bloco.append(botoes)
        self.rotulo_um_lado = rotulo("", "dim", wrap=True)
        bloco.append(self.rotulo_um_lado)
        return bloco

    def _rodar_guarda(self, argumentos, aviso):
        """Roda o script do protetor numa thread e mostra a saída embaixo dos botões."""
        if not os.path.exists(dispositivos.SCRIPT_GUARDA):
            self.rotulo_um_lado.set_text(f"Script não encontrado: {dispositivos.SCRIPT_GUARDA}")
            return
        self.rotulo_um_lado.set_text(aviso)
        self.botao_canais.set_sensitive(False)
        self.botao_reparar.set_sensitive(False)

        def rodar():
            try:
                r = subprocess.run([sys.executable if os.path.exists(sys.executable) else "python3",
                                    dispositivos.SCRIPT_GUARDA, *argumentos],
                                   capture_output=True, text=True, timeout=30)
                return (r.stdout + r.stderr).strip() or ("ok" if r.returncode == 0 else f"saiu com {r.returncode}")
            except (OSError, subprocess.TimeoutExpired) as erro:
                return f"falhou: {erro}"

        def terminou(texto):
            self.botao_canais.set_sensitive(True)
            self.botao_reparar.set_sensitive(True)
            self.rotulo_um_lado.set_text(texto.splitlines()[-1] if texto else "")

        em_segundo_plano(rodar, terminou)

    def _aba_estabilidade(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        numeros = Gtk.Box(spacing=14, homogeneous=True)
        self.n_hora = self._bloco_numero(numeros, "ÚLTIMA 1 H", "Reinícios do dongle nos últimos 60 minutos.")
        self.n_dia = self._bloco_numero(numeros, "ÚLTIMAS 24 H", "Reinícios do dongle nas últimas 24 horas.")
        self.n_ultimo = self._bloco_numero(numeros, "ÚLTIMO", "Data e hora do reinício mais recente.")
        caixa.append(numeros)
        caixa.append(rotulo("REINÍCIOS POR HORA", "secao"))
        self.barras = dica(BarrasPorHora(160),
                           "Reinícios do dongle por hora nas últimas 24 h (barra da direita = hora atual).")
        caixa.append(self.barras)
        self.rotulo_estab = rotulo("", "texto-ajuda", wrap=True)
        caixa.append(self.rotulo_estab)
        caixa.append(rotulo(
            "Cada reinício aparece no log do kernel como um aparelho 0e8d:0003 (o chip MediaTek do dongle em "
            "modo de recuperação) por cerca de 1 s. Com o problema de 28/10, ele reiniciava a cada ~150 s "
            "enquanto havia áudio tocando (~24 por hora). O áudio corta a cada reinício. Com o protetor "
            "ligado (aba Proteção), o esperado é nenhum reinício.",
            "texto-ajuda", wrap=True))
        return self.rolavel(caixa)

    @staticmethod
    def _bloco_numero(caixa, titulo, explicacao):
        bloco = dica(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["bloco"]), explicacao)
        bloco.append(rotulo(titulo, "secao"))
        valor = rotulo("…", "valor-medio")
        bloco.append(valor)
        caixa.append(bloco)
        return valor

    def _aba_protecao(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        linha = Gtk.Box(spacing=16, css_classes=["bloco"])
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        textos.append(rotulo("PROTEÇÃO CONTRA QUEDAS", "secao"))
        self.rotulo_servico = rotulo("verificando o serviço...", "dim", wrap=True)
        textos.append(self.rotulo_servico)
        linha.append(textos)
        self.chave_guarda = dica(Gtk.Switch(valign=Gtk.Align.CENTER), DICA_PROTETOR)
        self.chave_guarda.connect("state-set", self._guarda_mudou)
        linha.append(self.chave_guarda)
        caixa.append(linha)

        caixa.append(rotulo("ESTADO DO SERVIÇO", "secao"))
        self.caixa_guarda = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caixa.append(self.caixa_guarda)
        caixa.append(rotulo(
            "O temporizador do dongle conta a partir do início do áudio. O serviço do usuário "
            "alienware-headset-guard.service (aw725h-headset-disconnect-fix/aw725h_guard.py) roda em segundo plano, mesmo "
            "com o painel fechado: depois de 110 s de áudio contínuo, fecha e reabre o áudio do headset "
            "(corte de ~0,5 s) e o dongle não chega a reiniciar. O estado fica em "
            "~/.local/state/aw725h-guard/status.json. O interruptor usa systemctl --user enable --now / "
            "disable --now.", "texto-ajuda", wrap=True))
        return self.rolavel(caixa)

    def _aba_audio(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.rotulo_audio = rotulo("procurando o headset no PipeWire...", "dim", wrap=True)
        caixa.append(self.rotulo_audio)
        self.saida = self._bloco_audio(
            caixa, "saida", "SAÍDA (FONES)",
            "Usar como saída padrão",
            "Manda o som do computador para o headset (wpctl set-default). Os apps que já estão tocando "
            "podem continuar na saída antiga até serem reabertos.",
            "Volume dos fones de 0 a 100% (wpctl set-volume). Muda na hora.",
            "Silencia os fones (wpctl set-mute). Não desliga o headset.")
        self.entrada = self._bloco_audio(
            caixa, "entrada", "ENTRADA (MICROFONE)",
            "Usar como entrada padrão",
            "Usa o microfone do headset como entrada padrão do sistema (wpctl set-default).",
            "Volume do microfone de 0 a 100% (wpctl set-volume). Muda na hora.",
            "Silencia o microfone no computador (wpctl set-mute). O botão de mudo do próprio headset é outro.")
        caixa.append(rotulo(
            "Os números dos nós do PipeWire mudam a cada reinício do dongle, então o painel procura o "
            "AW725H de novo antes de cada ajuste.", "texto-ajuda", wrap=True))
        return self.rolavel(caixa)

    def _bloco_audio(self, caixa, tipo, titulo, texto_padrao, dica_padrao, dica_volume, dica_mudo):
        bloco = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["bloco"])
        topo = Gtk.Box(spacing=10)
        topo.append(rotulo(titulo, "secao", hexpand=True))
        estado = rotulo("", "ciano")
        topo.append(estado)
        bloco.append(topo)
        linha = Gtk.Box(spacing=12)
        padrao = dica(Gtk.Button(label=texto_padrao.upper(), css_classes=["contorno"]), dica_padrao)
        padrao.connect("clicked", lambda _b: self._definir_padrao(tipo))
        linha.append(padrao)
        linha.append(rotulo("", hexpand=True))
        linha.append(rotulo("Mudo", "dim"))
        mudo = dica(Gtk.Switch(valign=Gtk.Align.CENTER), dica_mudo)
        mudo.connect("notify::active", lambda s, _p: self._mudo_mudou(tipo, s.get_active()))
        linha.append(mudo)
        bloco.append(linha)
        volume_linha = Gtk.Box(spacing=12)
        volume = dica(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1), dica_volume)
        volume.set_hexpand(True)
        volume.connect("value-changed", lambda s: self._volume_mudou(tipo, s.get_value()))
        volume_linha.append(volume)
        valor = rotulo("—", "valor-medio", width_chars=4, xalign=1)
        volume_linha.append(valor)
        bloco.append(volume_linha)
        caixa.append(bloco)
        return {"estado": estado, "padrao": padrao, "mudo": mudo, "volume": volume, "valor": valor,
                "bloco": bloco, "pendente": None}

    # =====================================================================
    # Leituras
    # =====================================================================

    def _timer(self):
        """A cada 10 s, com a página aberta: estado sempre; áudio/proteção na aba deles; reinícios a cada 60 s."""
        self.voltas += 1
        if self.get_mapped():
            self.ler_estado()
            aba = self.abas.atual()
            if aba == "audio":
                self.ler_audio()
            elif aba == "protecao":
                self.ler_guarda()
            elif aba == "estabilidade" and self.voltas % 6 == 0:
                self.ler_reinicios()
        return True

    def _aba_aberta(self, nome):
        {"estado": self.ler_estado, "estabilidade": self.ler_reinicios,
         "protecao": self.ler_guarda, "audio": self.ler_audio}[nome]()

    def ao_mostrar(self):
        super().ao_mostrar()
        self.atualizar_tudo()

    def atualizar_tudo(self):
        """↻ ATUALIZAR: relê conexão, reinícios, serviço, áudio e a aba nova aberta. Nada vai ao headset."""
        self.ler_estado()
        self.ler_reinicios()
        self.ler_guarda()
        self.ler_audio()
        aba = self.extras.abas.get(self.abas.atual()) if hasattr(self, "extras") else None
        if aba:
            aba.atualizar()

    def ao_clicar_zona(self, zona):
        """Clique numa cabeça de alienígena do 3D: abre a aba Luz (pré-visualização da cor do logo)."""
        self.abas.mostrar("iluminacao")

    def ler_estado(self):
        headset = dispositivos.achar_headset()
        while (filho := self.caixa_estado.get_first_child()):
            self.caixa_estado.remove(filho)
        if headset is None:
            self.cabecalho.set_markup('DONGLE  <span foreground="#ffb020">○</span> DESCONECTADO')
            self.subcabecalho.set_text("413c:ab2b não encontrado (pode estar reiniciando)")
            self.definir_status("Dongle do AW725H não encontrado agora. Se ele está reiniciando, "
                                "volta em poucos segundos.", False)
            self.caixa_estado.append(grade_info([("Conexão", "desconectado")]))
            return
        self.cabecalho.set_markup('DONGLE  <span foreground="#00c8d7">●</span> '
                                  '<span foreground="#ffffff">CONECTADO</span>')
        bateria = self.extras.leitor.estado.get("bateria") if hasattr(self, "extras") else None
        texto_bateria = f"bateria {bateria}%" if bateria is not None else "bateria não informada ainda"
        self.subcabecalho.set_text(f"porta {headset['porta']} · {headset['velocidade']} · {texto_bateria}")
        self.subcabecalho.set_tooltip_text(
            "O AW725H tem UMA bateria interna que alimenta os dois lados, por isso o painel mostra um valor só. "
            "Ele vem do aviso que o dongle manda sozinho quando o nível muda (detalhes na aba Bateria).")
        self.definir_status(f"{headset['produto']} conectado na porta {headset['porta']} · {headset['id']}", True)
        self.caixa_estado.append(grade_info([
            ("Conexão", "conectado (dongle sem fio 2.4G)"),
            ("Produto", f"{headset['fabricante']} {headset['produto']}"),
            ("ID USB", headset["id"]),
            ("Porta", headset["porta"]),
            ("Velocidade", headset["velocidade"]),
            ("Firmware instalado", f"dongle {headset['versao']} (bcdDevice)"),
            ("Mais recente", dispositivos.FIRMWARE_RECENTE),
        ]))
        if dispositivos.dongle_desatualizado(headset["versao"]):
            self.caixa_estado.append(rotulo(
                f"O dongle informa {headset['versao']}: provavelmente abaixo do mais recente (dongle 1.1.0). "
                "Atualizar no Windows pode resolver os reinícios.", "aviso", wrap=True, margin_top=12))

    def ler_reinicios(self):
        if self.lendo_reinicios:
            return
        self.lendo_reinicios = True
        em_segundo_plano(dispositivos.reinicios_headset, self._mostrar_reinicios)

    def _mostrar_reinicios(self, dados):
        self.lendo_reinicios = False
        if dados["erro"]:
            self.rotulo_estab.set_text(f"Não consegui ler o log do kernel: {dados['erro']}")
        self.n_hora.set_text(str(dados["hora"]))
        self.n_dia.set_text(str(dados["dia"]))
        self.n_ultimo.set_text(dados["ultimo"][6:] if dados["ultimo"] else "nenhum")
        self.n_ultimo.set_tooltip_text(f"Último reinício: {dados['ultimo'] or 'nenhum nas últimas 24 h'}")
        self.barras.definir(dados["por_hora"])
        if not dados["erro"]:
            if dados["hora"] >= 10:
                situacao = "Instável: o dongle está reiniciando sem parar nesta hora."
            elif dados["hora"] > 0:
                situacao = "Alguns reinícios na última hora."
            else:
                situacao = "Estável na última hora."
            self.rotulo_estab.set_text(situacao)
            if dados["hora"] >= 10:
                self.rotulo_estab.add_css_class("aviso")
            else:
                self.rotulo_estab.remove_css_class("aviso")

    def ler_guarda(self):
        def ler():
            existe = dispositivos.servico_existe()
            return existe, existe and dispositivos.servico_ligado(), dispositivos.status_guarda()
        em_segundo_plano(ler, self._mostrar_guarda)

    def _mostrar_guarda(self, resultado):
        existe, ligado, status = resultado
        self.atualizando = True
        self.chave_guarda.set_active(ligado)
        self.chave_guarda.set_state(ligado)
        self.atualizando = False
        if not existe:
            self.rotulo_servico.set_text("Serviço não encontrado: instale com aw725h-headset-disconnect-fix/install.sh "
                                         "(ou ./install.sh --headset-fix na raiz do repositório).")
        else:
            self.rotulo_servico.set_text("Ligada: reabre o áudio a cada ~110 s." if ligado else "Desligada.")
        while (filho := self.caixa_guarda.get_first_child()):
            self.caixa_guarda.remove(filho)
        if status is None:
            self.caixa_guarda.append(rotulo("Sem dados (~/.local/state/aw725h-guard/status.json ainda não existe).",
                                            "dim"))
            return
        reinicios = status.get("resets_detected")
        valores = {
            "active": "sim" if status.get("active") else "não",
            "mode": modo_legivel(status.get("mode")),
            "resets_detected": "sem acesso ao log do kernel" if reinicios is None else reinicios,
        }
        nomes = [("active", "Ativo"), ("mode", "Modo"), ("interventions", "Intervenções"),
                 ("last_intervention", "Última intervenção"), ("resets_detected", "Reinícios detectados"),
                 ("since", "Ligado desde"), ("updated", "Atualizado em")]
        pares = []
        for chave, nome in nomes:
            valor = valores.get(chave, status.get(chave))
            pares.append((nome, str(valor) if valor not in (None, "") else "—"))
        self.caixa_guarda.append(grade_info(pares))

    def ler_audio(self):
        def ler():
            nos = dispositivos.nos_audio_headset()
            volumes = {tipo: dispositivos.ler_volume(nos[tipo]) if nos[tipo] is not None else (None, False)
                       for tipo in ("saida", "entrada")}
            return nos, volumes
        em_segundo_plano(ler, self._mostrar_audio)

    def _mostrar_audio(self, resultado):
        nos, volumes = resultado
        self.nos = nos
        if nos["erro"]:
            self.rotulo_audio.set_text(f"Não consegui falar com o PipeWire: {nos['erro']}")
        elif nos["saida"] is None and nos["entrada"] is None:
            self.rotulo_audio.set_text("O AW725H não aparece no PipeWire agora (dongle desligado ou reiniciando).")
        else:
            self.rotulo_audio.set_text(f"Nós do PipeWire: saída {nos['saida']}, entrada {nos['entrada']}.")
        self.atualizando = True
        for tipo, bloco in (("saida", self.saida), ("entrada", self.entrada)):
            volume, mudo = volumes[tipo]
            existe = nos[tipo] is not None and volume is not None
            bloco["bloco"].set_sensitive(existe)
            padrao = nos[f"{tipo}_padrao"]
            bloco["estado"].set_text("● PADRÃO" if padrao else ("não é o padrão" if existe else "indisponível"))
            bloco["padrao"].set_sensitive(existe and not padrao)
            if existe and bloco["pendente"] is None:  # não atropela um ajuste que você está fazendo
                bloco["volume"].set_value(round(min(volume, 1.0) * 100))
                bloco["valor"].set_text(f"{round(volume * 100)}%")
                bloco["mudo"].set_active(mudo)
        self.atualizando = False

    # =====================================================================
    # Ações (só acontecem quando você mexe nos controles)
    # =====================================================================

    def _guarda_mudou(self, _chave, ligar):
        if self.atualizando:
            return False
        self.rotulo_servico.set_text("ligando..." if ligar else "desligando...")
        em_segundo_plano(lambda: dispositivos.ligar_servico(ligar), self._guarda_terminou)
        return True  # o estado visual só muda depois de ler de novo

    def _guarda_terminou(self, resultado):
        ok, mensagem = resultado
        if not ok:
            self.rotulo_servico.set_text(f"Falhou: {mensagem}")
        GLib.timeout_add(800, lambda: self.ler_guarda() and False)

    def _abrir_guia(self):
        if not os.path.exists(dispositivos.GUIA_HEADSET):
            self.rotulo_guia.set_text(f"Guia não encontrado: {dispositivos.GUIA_HEADSET}")
            return
        self.rotulo_guia.set_text("")
        subprocess.Popen(["xdg-open", dispositivos.GUIA_HEADSET])

    def _no_atual(self, tipo):
        """Procura o nó de novo, porque o número muda quando o dongle reinicia."""
        return dispositivos.nos_audio_headset()[tipo]

    def _definir_padrao(self, tipo):
        def fazer():
            no = self._no_atual(tipo)
            return no is not None and dispositivos.definir_padrao(no)
        em_segundo_plano(fazer, lambda _ok: self.ler_audio())

    def _volume_mudou(self, tipo, valor):
        bloco = self.saida if tipo == "saida" else self.entrada
        bloco["valor"].set_text(f"{round(valor)}%")
        if self.atualizando:
            return
        # Espera você parar de arrastar (250 ms) antes de chamar o wpctl
        if bloco["pendente"]:
            GLib.source_remove(bloco["pendente"])
        bloco["pendente"] = GLib.timeout_add(250, self._aplicar_volume, tipo)

    def _aplicar_volume(self, tipo):
        bloco = self.saida if tipo == "saida" else self.entrada
        bloco["pendente"] = None
        volume = bloco["volume"].get_value() / 100

        def fazer():
            no = self._no_atual(tipo)
            return no is not None and dispositivos.definir_volume(no, volume)
        em_segundo_plano(fazer, lambda _ok: None)
        return False

    def _mudo_mudou(self, tipo, mudo):
        if self.atualizando:
            return

        def fazer():
            no = self._no_atual(tipo)
            return no is not None and dispositivos.definir_mudo(no, mudo)
        em_segundo_plano(fazer, lambda _ok: None)
