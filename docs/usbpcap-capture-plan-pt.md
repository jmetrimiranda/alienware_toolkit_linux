# Plano de captura no Windows (USBPcap): luz, bateria e ajustes do AW725H

Objetivo: descobrir os comandos que o Alienware Command Center (AWCC) manda ao dongle do
AW725H (413c:ab2b) para **mudar a luz do logo**, **pedir a bateria** e ler o estado do headset.
No Linux o painel só **lê** o canal HID (nada é enviado), então estes comandos precisam vir de
uma captura real. Regra do projeto: implementar só o que aparecer na captura, nunca "chutar" bytes.

## 1. O que já se sabe (Linux, 29/10/2026)

| Item | Valor |
|---|---|
| Dongle | 413c:ab2b "Dell Inc AW725H Dongle", firmware do dongle 1.00 (bcdDevice) |
| Interface HID | interface 3 (`1-2:1.3`), só endpoint IN `0x83` (64 bytes) |
| Canal de fabricante | usage page `0xFF13`: report **6** saída (61 bytes), report **7** entrada (61 bytes), report **8** entrada (7 bytes) |
| Consumer control | report **2**: volume +/−, mudo, play/pausa, próxima, anterior (1 bit cada) |
| Avisos já decifrados (escuta passiva) | report **8** `08 c0 09 03 00 <subtipo> <valor> <xor>` (xor de todos os bytes anteriores). Subtipo 02 = bateria % (27→18 em uso; sobe a cada 18 s carregando); subtipo 01 = dois estados `0xdd`/`0xcc`, a decifrar. Ver [`data/aw725h-hid-listen-analysis.md`](data/aw725h-hid-listen-analysis.md). |
| Consequência | Sem endpoint OUT, o AWCC manda o report 6 por **SET_REPORT** no endpoint de controle (`bmRequestType 0x21`, `bRequest 0x09`, `wValue 0x0206`, `wIndex 3`). As respostas devem chegar no `0x83` como report 7 (ou por GET_REPORT, `wValue 0x0107`). |

## 2. Preparação (Alienware Area-51, Windows)

1. Atualize o AWCC para 6.4 ou mais novo (o AW725H exige). **Não** rode atualização de
   firmware durante a captura.
2. Instale o Wireshark marcando **USBPcap** no instalador (reinicie se pedir).
3. No Gerenciador de Dispositivos → Exibir → *Dispositivos por conexão*, ache o dongle e anote
   em qual *USB Root Hub* ele está (o USBPcap captura por hub: USBPcap1, USBPcap2...).
4. Deixe o headset carregado, ligado e conectado pelo dongle (não por Bluetooth: o AWCC não
   configura o headset por Bluetooth).
5. Feche outros apps de áudio. Tenha um bloco de notas aberto para anotar **hora + ação**.

## 3. Sessões de captura (um arquivo `.pcapng` por sessão)

Em cada sessão: inicie a captura no hub certo, espere 5 s, faça as ações com ~5 s entre elas,
anote o horário de cada uma, espere 5 s e pare.

| # | Arquivo | Ações (anote a hora de cada uma) |
|---|---|---|
| 1 | `01-abrir-awcc.pcapng` | Com o AWCC fechado, inicie a captura e abra o AWCC até a página do headset aparecer (enumeração, versão, bateria). Deixe 60 s parado na página (consulta periódica de bateria?). |
| 2 | `02-bateria.pcapng` | Na página do headset: anote a % mostrada; ligue o cabo de carga no headset; espere o AWCC mostrar "carregando"; tire o cabo. |
| 3 | `03-luz-cores.pcapng` | Efeito fixo: vermelho `#FF0000`, verde `#00FF00`, azul `#0000FF`, branco `#FFFFFF`, nesta ordem. |
| 4 | `04-luz-brilho.pcapng` | Cor fixa vermelha com brilho 100, 50, 10, 0. Depois *Go Dark*, *Go Dim*, *Go Light*. |
| 5 | `05-luz-efeitos.pcapng` | Cada efeito disponível (respirar, espectro, transição/morph, pulsar...) com cores simples e, se houver, velocidade mínima e máxima. |
| 6 | `06-botoes.pcapng` | Botão de mudo do microfone (liga/desliga), recolher e estender o microfone, botão Game/Chat (cima, baixo, apertar), roda de volume. |
| 7 | `07-liga-desliga.pcapng` | Desligar o headset, esperar 10 s, ligar de novo (estado de conexão). |
| 8 | `08-ajustes.pcapng` | Se esta versão do AWCC mostrar EQ, sidetone, desligamento automático ou outros ajustes para o AW725H: mudar cada um de um extremo ao outro. |
| — | **Não capturar** | Atualização de firmware e "Restaurar padrões de fábrica" (risco de estragar o dongle ou apagar a configuração). |

## 4. Exportar só o que interessa

1. No Wireshark, ache o endereço do dongle: filtro `usb.idVendor == 0x413c && usb.idProduct == 0xab2b`
   (aparece no *GET DESCRIPTOR*); anote `usb.device_address` (ex.: 7).
2. Filtro de trabalho: `usb.device_address == 7 && (usb.setup.bRequest == 0x09 || usb.setup.bRequest == 0x01 || usb.endpoint_address == 0x83)`.
3. *File → Export Specified Packets* (só os exibidos) para cada sessão.
4. Tabela de texto (cole junto com as anotações de horário):

   ```
   tshark -r 03-luz-cores.pcapng -Y "usb.device_address == 7" -T fields ^
     -e frame.time_relative -e usb.endpoint_address -e usb.setup.bRequest -e usb.setup.wValue ^
     -e usb.data_fragment -e usbhid.data -e usb.capdata > 03-luz-cores.tsv
   ```

5. Traga os `.pcapng`, os `.tsv` e as anotações para o Linux (ou anexe numa issue do repositório). Para ler sem o Wireshark: `python3 -I tools/ler_pcap_usbpcap.py arquivo.pcapng --todos`.

## 5. Análise no Linux

1. Para cada ação, isolar os SET_REPORT do report 6 e as respostas do report 7 logo depois.
2. Comparar pares de capturas que mudam **uma coisa só** (vermelho × verde → bytes de cor;
   brilho 100 × 50 → byte de brilho; efeito A × B → byte de efeito). Procurar cabeçalho fixo,
   comprimento, checksum.
3. Conferir se a % mostrada no AWCC bate com o subtipo 02 do aviso `c0 09` (report 8) e achar o
   comando do report 6 que pede a bateria na hora (resposta provável no report 7, talvez `40 …`/`c0 …`).
   Na sessão 6, anotar o que o subtipo 01 (`0xdd`/`0xcc`) faz: mudo, microfone recolhido ou outro.
4. Escrever os comandos em `alienware-command-center-linux/headset_aw725h.py` com o valor capturado, um por vez, e testar com o
   headset carregado: primeiro a leitura da bateria, depois uma cor fixa. Nada de varrer valores.
5. Só depois disso trocar a aba "Luz" de pré-visualização para "aplicar no headset".

## 6. Por que não descobrir no Linux mesmo?

O canal é proprietário e sem documentação pública (HeadsetControl, alienfx-tools e OpenRGB não
suportam headsets Alienware; o APIv7 do mouse AW720M usa outro formato, 64 bytes sem report ID).
Mandar bytes no escuro pelo report 6 pode mudar a configuração salva no headset ou deixar o
dongle num estado ruim, e esse dongle já tem um firmware instável (reinícios a cada ~150 s de
áudio sem o protetor). A captura do AWCC dá os comandos reais com risco zero.
