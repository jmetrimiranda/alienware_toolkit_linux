> **Caderno de desenvolvimento de 29/10/2026 (histórico).** Este é o `plan.md` original, mantido como
> registro de como o protocolo foi descoberto. Os caminhos citados abaixo são os da época; o repositório
> foi reorganizado depois. Para usar o projeto, siga o [README](../README.md).
>
> | Caminho antigo | Caminho novo |
> |---|---|
> | `conserto_headset/` | [`aw725h-headset-disconnect-fix/`](../aw725h-headset-disconnect-fix/) |
> | `executar.sh` | [`alienware-command-center-linux/run.sh`](../alienware-command-center-linux/) |
> | `instalar_permissao.sh` | [`install.sh`](../install.sh) (raiz) / `udev/install-udev-rules.sh` |
> | `sondar.py`, `teste_guiado.sh`, `monitor_headset.sh` | [`tools/`](../tools/) |
> | `70-alienware-aw720m.rules` | [`udev/70-alienware-toolkit.rules`](../udev/70-alienware-toolkit.rules) |
> | `app.py`, `ui/`, `aw720m.py`, `dispositivos.py` | [`alienware-command-center-linux/`](../alienware-command-center-linux/) |
> | `plan.md` | este arquivo (`docs/development-notes-pt.md`) |
>
> Versão técnica em inglês do protocolo do mouse: [aw720m-mouse-hid-protocol.md](aw720m-mouse-hid-protocol.md).

# Painel Linux para o Alienware AW720M

Interface gráfica (GTK4 + libadwaita) para ver a bateria, mudar a cor e, mais tarde, outras configurações do mouse Alienware AW720M no Ubuntu do H110, sem o Alienware Command Center (AWCC, só Windows).

## 1. Contexto (diagnóstico de 29/10/2026)

| Item | Achado |
|---|---|
| Bluetooth | **O PC não tem Bluetooth.** O adaptador USB MediaTek MT7921U (0e8d:7961) só expõe a interface de Wi-Fi. Não existe `/sys/class/bluetooth`, o `btusb` não está carregado e o `bluetooth.service` é pulado (`ConditionPathIsDirectory=/sys/class/bluetooth`). Por isso o GNOME mostra "No Bluetooth Found". |
| Conexão do mouse | **413c:3029 = dongle 2.4G** (o dongle USB-C no extensor ligado pelo cabo). O mouse no cabo USB-C aparece como **413c:3028** (bluez issue #2680). |
| Interfaces do dongle | `If 0` mouse (11 bytes: botões, X/Y 16 bits, roda, **5 bytes de fabricante**), `If 1` teclado (botões programáveis), `If 2` fabricante 0xFF00 com 64 bytes IN/OUT, sem report ID → é por ela que o AWCC configura o mouse. |
| Bateria no Linux | Não aparece: o mouse não usa o "Battery Strength" padrão do HID, então o kernel não cria `power_supply` e o `upower` não vê nada. |
| Software pronto | Não existe para o AW720M. libratbag/Piper (126 aparelhos), OpenRGB (só AW410K/AW510K e LEDs da Dell G Series), OpenMouse e Solaar não suportam. |
| Permissão | `/dev/hidraw*` é `root 0600`. É preciso uma regra udev (uma vez, com sudo). |

## 2. É factível?

| Recurso | Viabilidade | Por quê |
|---|---|---|
| Interface gráfica, detectar dongle/cabo | **Sim (pronto)** | sysfs + GTK4 já instalados. |
| Mudar a cor | **Funciona (29/10/2026)** | O protocolo "APIv7" do alienfx-tools (T-Troll), feito para o AW610M, funcionou no AW720M pelo dongle: Jorge trocou de cor várias vezes pelo painel. O comando de status respondeu `40 03 03 00 ec ac`, ainda sem significado conhecido. |
| Ver a bateria | **Provável, falta descobrir o comando** | O AWCC mostra a bateria pelo dongle, então a informação passa pela USB. Falta saber em qual relatório e em qual byte ela vem. |
| DPI, polling, LOD, economia de energia | **Possível, com captura** | Exige gravar o tráfego do AWCC no Windows (Fase 3). |
| Macros, atualização de firmware | **Fora do escopo** | Risco alto (pode travar o mouse ou o dongle). Usar o AWCC no Windows. |

## 3. Arquitetura

```
app.py  (GTK4/libadwaita)  ─┐
sondar.py  (linha de comando) ┼─> aw720m.py ──> /dev/hidrawN (If 2, 64 bytes) ──> dongle ──> mouse
                              └─> aw720m.escutar_extras_do_mouse ──> /dev/hidrawM (If 0, só leitura)
```

| Arquivo | Função |
|---|---|
| `aw720m.py` | Acha o dongle/cabo no sysfs, abre o hidraw, envia/recebe relatórios de 64 bytes e guarda os comandos conhecidos. |
| `app.py` | Janela: conexão, bateria, cor/zona/efeito/brilho, diagnóstico com log em hexadecimal e botão "Dar permissão" (pkexec). |
| `sondar.py` | A mesma coisa pela linha de comando, salvando em `logs/` para comparar. |
| `70-alienware-aw720m.rules` | Regra udev `TAG+="uaccess"` para 413c:3028/3029. |
| `instalar_permissao.sh` | Instala a regra e recarrega o udev (pede sudo). |
| `executar.sh` | Abre o app com o `.venv`. |
| `.venv/` | Python 3.12 com `--system-site-packages` (usa o PyGObject do sistema) + `hid-tools` para investigação. |

## 4. Protocolo conhecido (APIv7, do alienfx-tools)

O kernel retira o byte 0x00 do report ID. Os bytes que vão ao mouse são:

| Comando | Bytes | Observação |
|---|---|---|
| Status | `40 03 01 00 01` | Pede o estado. Não é usado pelo alienfx-tools; candidato para bateria. |
| Cor/efeito | `40 10 0c 00 EF BR ZN R G B R2 G2 B2` | EF = efeito (1 fixo, 2 respirar, 3 transição, 4 espectro, 5 pulsar, 6 arco-íris); BR = brilho 0–100; ZN = zona (AW610M: 0 luz, 1 logo). |
| Atualizar | `40 60 07 00 c0 4e 00 01` | Existe no SDK, mas o alienfx-tools não envia para mouses. |

Cada comando gera uma resposta de 64 bytes na mesma interface. A resposta padrão é `40 <cmd> 03 00 ec ac` (OK).

### Descobertas do teste guiado (29/10/2026, `logs/gravacao-20261029-074236.txt`)

| Sinal | Significado |
|---|---|
| `c0 0a 09 00 01 14 CC 00 VV VV TT EE` | **Aviso de energia, enviado pelo mouse sozinho** ao encostar ou tirar o carregador. Byte 5 = **bateria em %** (0x14 = 20, provável). Byte 6 (CC) = 1 com carregador, 0 sem. Byte 11 (EE) = 2 carregando. Os bytes 8–9 (0x02f7 = 759) podem ser tensão ou leitura bruta; o byte 10 (0x13) ainda é desconhecido. |
| `c0 07 0a ... b0` / `c0 07 0a` | Pares de eventos vistos só na 1ª escuta; não são clique, roda, DPI nem carregador. Ainda sem explicação. |
| Interface 0, bytes 6–10 | O byte 6 vale sempre `03`; o byte 7 muda só no **clique esquerdo** (valor aleatório) e volta a 0. Não é bateria. |
| Botão de DPI | Chega ao sistema como **botão 5** (bit 0x10 do byte de botões). |

O painel escuta o aviso `c0 0a` o tempo todo e guarda o último valor em `logs/bateria.json`. Pendente: achar um comando que **peça** a bateria (hoje o valor só chega quando o estado do carregador muda) e confirmar se o byte 5 é mesmo a porcentagem, vendo se ele sobe durante a carga.

## 5. Fases

**Fase 0: permissão (1 min, precisa de você).** Rodar `sudo ./instalar_permissao.sh` ou clicar em "Dar permissão" no app.

**Fase 1: escuta passiva (segura, sem enviar nada).**
1. `python sondar.py extras 20`: mexer o mouse e ver se algum dos 5 bytes extras é um número entre 0 e 100 ou muda ao encostar o carregador magnético.
2. `python sondar.py escutar 60`: ver se o dongle manda algo sozinho (bateria, DPI) ao apertar o botão de DPI ou ao encostar o carregador.

**Fase 2: comandos conhecidos (risco baixo).**
1. `python sondar.py status`: guardar a resposta e procurar um byte que bata com a bateria (comparar com a carga cheia e com a bateria mais baixa).
2. `python sondar.py cor 255 0 0 0` e `... 1`: confirmar a cor e as zonas.
3. Se a cor funcionar, o app já fica útil para iluminação.

**Fase 3: captura no Windows (se as Fases 1 e 2 não acharem a bateria).**
1. No Alienware Area-51: instalar Wireshark com USBPcap e o AWCC.
2. Gravar enquanto: abre o AWCC (ele lê a bateria), muda a cor, muda o DPI, o polling e o LOD.
3. Filtrar `usb.idVendor == 0x413c` e exportar só os relatórios OUT/IN de 64 bytes da interface 2.
4. Trazer o `.pcapng` para cá. Implementar só os comandos vistos na captura, sem tentativa no escuro.

**Fase 4: acabamento.**
- Bateria atualizando a cada 5 minutos e alerta abaixo de 15%.
- Atalho no menu de aplicativos (`.desktop`).
- Opcional: publicar a bateria no `upower` (como o OpenRazer faz) para aparecer no menu de energia do GNOME.

## 6. Riscos e cuidados

- **Comandos desconhecidos podem alterar as configurações salvas no mouse.** Por isso: primeiro escuta passiva, depois só comandos documentados ou capturados. Nunca varrer comandos aleatórios.
- **Firmware:** não mexer. A Dell avisa que interromper uma atualização pode estragar o mouse ou o dongle.
- **Modo com cabo (413c:3028):** o `97-hid2hci.rules` do bluez pode desligar o mouse ao conectar o cabo direto nele (bluez issue #2680). Correção, se acontecer: copiar `/usr/lib/udev/rules.d/97-hid2hci.rules` para `/etc/udev/rules.d/` e acrescentar `ATTRS{product}!="*AW720M*"` à linha da Dell.
- **Bluetooth:** seria o caminho mais simples para a bateria (o BLE tem Battery Service padrão), mas o PC não tem Bluetooth. Um adaptador USB (ex.: Realtek RTL8761B) resolveria só a bateria, não a cor.

## 7. Como usar

```bash
cd ~/Desktop/alienware
sudo ./instalar_permissao.sh        # uma vez
./executar.sh                       # abre o painel
.venv/bin/python sondar.py extras 20   # investigação pela linha de comando
```

## 8. Interface v2 (29/10/2026)

Painel reescrito no estilo do Alienware Command Center: tema escuro forçado, acento ciano `#00c8d7`, títulos finos em caixa alta ("ALIENFX │ DISPOSITIVOS"), barra lateral só com ícones e logo próprio (`assets/logo.svg`, desenho original).

| Parte | O que faz |
|---|---|
| `app.py` | Entrada: tema (`estilo.css`) + janela. Modo de captura: `ALIENWARE_CAPTURA=arq.png ALIENWARE_PAGINA=inicio\|mouse[:aba]\|headset[:aba]\|outro` salva a janela em PNG e sai (`ALIENWARE_ESPERA` = segundos, padrão 2,5). |
| `ui/janela.py` | Barra lateral (Início, Dispositivo, Configurações, Sobre) e a pilha de páginas. |
| `ui/pagina_inicio.py` | Cartões dos aparelhos USB (sem hubs), atualizados a cada 2 s. Suportados: AW720M e AW725H; os demais abrem "Somente informações" (`ui/pagina_info.py`). |
| `ui/pagina_mouse.py` | Abas Iluminação (roda de cores, hexadecimal, amostras saturadas, zonas, efeito, 2ª cor, brilho 0–100, "Cores vivas"), Bateria e Diagnóstico (status, escutas, teste guiado, log). Nada vai ao mouse antes de **✓ APLICAR**; **✕ CANCELAR** volta à última configuração aplicada. |
| `ui/pagina_headset.py` | Abas Estado (firmware do dongle × mais recente e botão "Abrir guia" para `conserto_headset/README.md`), Estabilidade (reinícios 1 h/24 h e barras por hora via `journalctl -k`), Proteção (liga/desliga `alienware-headset-guard.service` e lê `~/.local/state/aw725h-guard/status.json`, chaves em inglês) e Áudio (`wpctl`: padrão, volume, mudo). |
| `ui/widgets.py` | Roda de cores, anel de bateria, ilustração SVG com brilho na cor escolhida, barras por hora, abas. |
| `dispositivos.py` | Leituras do sistema: USB (sysfs), reinícios, serviço, PipeWire. |

**Cores vivas (correção da luz "rala"):** o LED é linear, a tela tem gama ~2,2. Cores pastel (ex.: `#c061cb`, três canais acesos) saíam esbranquiçadas. `aw720m.corrigir_cor(r, g, b, gama=2.2)` aplica `c' = round(255·(c/255)^2,2)` antes de enviar (`#c061cb` → `#891e9a`), ligada por padrão. Para cor forte: cor saturada (amostras ou borda da roda), efeito fixo e brilho 100. Respirar e pulsar passam parte do tempo apagados e parecem mais fracos.

Testes: `py_compile`, SVGs validados com `xml.dom.minidom`, capturas em `capturas/` geradas no broadway (`gtk4-broadwayd :8`, `GDK_BACKEND=broadway BROADWAY_DISPLAY=:8`), sem tocar na tela e sem enviar cor ao mouse. O broadway simula uma tela de 1105×768, então as capturas saem nesse tamanho e não no padrão da janela (1280×800).

Instalação a partir do laboratório: ver `INSTALAR.md`.

## 9. Headset AW725H (29/10/2026)

Guia completo: `conserto_headset/README.md` (pacote mantido à parte, não vem desta pasta).

- **Causa:** com o firmware 1.00, o dongle (413c:ab2b) reinicia ~140–150 s depois que o **stream de áudio começa**, não depois da conexão USB. No experimento de 29/10, uma pausa às 08:03:15 adiou o reinício para 08:05:36 (141 s depois); a linha de base foi de 288 reinícios em 28–29/10, 286 com áudio tocando.
- **Contorno:** o protetor `alienware-headset-guard.service` (`conserto_headset/aw725h_guard.py`, systemd `--user`) reabre o PCM a cada 110 s de áudio contínuo: move os streams para um null-sink, suspende o sink do headset por 0,3 s e devolve (corte de ~0,5 s). Uma pausa curta sem fechar o PCM (16 ms) deixava o som de um lado só, por isso o PCM é fechado de verdade.
- **Estado:** `~/.local/state/aw725h-guard/status.json` (`active`, `interventions`, `last_intervention`, `resets_detected`, `mode`, `since`, `updated`), lido pela aba Proteção.
- **Regra do ModemManager** (para ele não sondar o dongle quando o chip reinicia): `conserto_headset/install.sh --udev`, **sem** `sudo` na frente (o script pede a senha só para copiar a regra; como root, o `systemctl --user` dele falharia).
- **Correção definitiva:** atualizar no Windows o firmware para headset 1.8.0 + dongle 1.1.0 (Dell, jul/2025, DSA-2025-303), os dois juntos. Depois disso, conferir com o protetor desligado: 0 reinícios em 30 min com áudio (`./monitor_headset.sh 30`).
