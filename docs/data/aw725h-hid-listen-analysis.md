# Análise da escuta passiva (escuta-20261029-090105.log)

- escuta passiva /dev/hidraw0 (O_RDONLY) início 2026-10-29 09:01:05
- hora		t(s)	id	bytes (hex, inclui o report id)
- fim 2026-10-29 09:27:06 contagem por report id: {8: 14}
- Duração coberta pelo contexto: 25.9 min; reports recebidos: 14
- Por report id: {8: 14}
- Report 8 com checksum XOR válido: 14 de 14

| Hora | t (s) | Bytes | Decifrado |
|---|---|---|---|
| 09:04:35.169 | 209.3 | `08 c0 09 03 00 02 1b db` | bateria 27% |
| 09:04:48.859 | 222.9 | `08 c0 09 03 00 01 dd 1e` | aviso 01 = 0xdd (a decifrar) |
| 09:05:18.222 | 252.3 | `08 c0 09 03 00 01 cc 0f` | aviso 01 = 0xcc (a decifrar) |
| 09:06:55.378 | 349.5 | `08 c0 09 03 00 02 1a da` | bateria 26% |
| 09:10:25.789 | 559.9 | `08 c0 09 03 00 02 19 d9` | bateria 25% |
| 09:12:45.980 | 700.1 | `08 c0 09 03 00 02 18 d8` | bateria 24% |
| 09:15:06.184 | 840.3 | `08 c0 09 03 00 02 17 d7` | bateria 23% |
| 09:17:26.383 | 980.5 | `08 c0 09 03 00 02 16 d6` | bateria 22% |
| 09:19:46.558 | 1120.7 | `08 c0 09 03 00 02 15 d5` | bateria 21% |
| 09:23:16.834 | 1330.9 | `08 c0 09 03 00 02 14 d4` | bateria 20% |
| 09:25:02.820 | 1436.9 | `08 c0 09 03 00 01 dd 1e` | aviso 01 = 0xdd (a decifrar) |
| 09:25:16.337 | 1450.4 | `08 c0 09 03 00 01 cc 0f` | aviso 01 = 0xcc (a decifrar) |
| 09:25:37.032 | 1471.1 | `08 c0 09 03 00 02 13 d3` | bateria 19% |
| 09:26:47.199 | 1541.3 | `08 c0 09 03 00 02 12 d2` | bateria 18% |

- **subtipo 01 (dois estados, a decifrar)**: 09:04:48=0xdd, 09:05:18=0xcc (+29.4 s), 09:25:02=0xdd (+1184.6 s), 09:25:16=0xcc (+13.5 s)
- **subtipo 02 (bateria %)**: 09:04:35=27, 09:06:55=26 (+140.2 s), 09:10:25=25 (+210.4 s), 09:12:45=24 (+140.2 s), 09:15:06=23 (+140.2 s), 09:17:26=22 (+140.2 s), 09:19:46=21 (+140.2 s), 09:23:16=20 (+210.3 s), 09:25:37=19 (+140.2 s), 09:26:47=18 (+70.2 s)
- Contexto: PCM de saída ['RUNNING'], captura ['closed'], volume do mixer ['60,60']
