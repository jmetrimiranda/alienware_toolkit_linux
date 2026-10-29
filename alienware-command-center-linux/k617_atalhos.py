"""Atalhos Fn do teclado Redragon K617 Fizz (tabela para a aba "Atalhos Fn" e para o README).

Fonte: manual do K617 Fizz RGB (https://gzhls.at/blob/ldb/6/7/e/0/fd543e7302a96b62efe1d68ad0c2f00ace1c.pdf,
"Key Function Introduction" e "Backlight setting", lido em 29/10/2026).
O K617 Fizz Rainbow (K617-R, USB 258a:002a) usa o mesmo gabinete de 61 teclas, mas os LEDs têm cor
fixa de fábrica por fileira: algumas combinações de luz do RGB não existem nele.

Cada item:
  teclas   texto mostrado ("Fn + M")
  ids      teclas no modelo 3D (ids do layout 60% de assets/3d/js/modelos/teclado.js), acesas ao escolher
  grupo    "luz", "sistema" ou "tecla"
  funcao   o que faz
  rainbow  "sim" (existe no Rainbow), "talvez" (no manual do RGB; pode não existir no Rainbow) ou "não"
"""

# Modos de luz do K617 RGB, na ordem do manual (Fn + Alt direito). O Rainbow tem os seus próprios modos.
MODOS_RGB = ["Go with the stream", "Clouds fly", "Winding Paths", "The trial of Light", "Breathing",
             "Normally on", "Pass without Trace", "Ripple Graff", "Swift action", "Digital Times",
             "Flowers blooming"]

ATALHOS = [
    {"teclas": "Fn + Alt direito", "ids": ["Fn", "AltR"], "grupo": "luz",
     "funcao": "Troca o modo de luz, em ciclo (no RGB são 11 modos: onda, respirar, fixo, reativo...)",
     "rainbow": "sim"},
    {"teclas": "Fn + M", "ids": ["Fn", "M"], "grupo": "luz",
     "funcao": "Brilho da luz: 5 níveis, em ciclo", "rainbow": "sim"},
    {"teclas": "Fn + ,", "ids": ["Fn", "Comma"], "grupo": "luz",
     "funcao": "Velocidade do efeito: 5 níveis, em ciclo", "rainbow": "sim"},
    {"teclas": "Fn + Espaço", "ids": ["Fn", "Space"], "grupo": "luz",
     "funcao": "Modo de escolher cor: o Espaço pisca nas cores e você aperta a tecla da cor. Só existe no "
               "K617 RGB; se nada piscar, o seu é o Rainbow", "rainbow": "não"},
    {"teclas": "Fn + Win", "ids": ["Fn", "WinL"], "grupo": "sistema",
     "funcao": "Trava a tecla Windows (bom para jogos); repita para destravar", "rainbow": "sim"},
    {"teclas": "Fn + Esc (segurar 3 s)", "ids": ["Fn", "Esc"], "grupo": "sistema",
     "funcao": "Volta às configurações de fábrica (luz, trava do Windows)", "rainbow": "talvez"},
    {"teclas": "Fn + 1 … 0, -, =", "ids": ["Fn", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Minus", "Equal"],
     "grupo": "tecla", "funcao": "F1 … F12", "rainbow": "sim"},
    {"teclas": "Fn + W / A / S / D", "ids": ["Fn", "W", "A", "S", "D"], "grupo": "tecla",
     "funcao": "Setas: W ↑, A ←, S ↓, D →", "rainbow": "sim"},
    {"teclas": "Fn + [ / ]", "ids": ["Fn", "LBr", "RBr"], "grupo": "tecla",
     "funcao": "Insert / Delete", "rainbow": "talvez"},
    {"teclas": "Fn + ; / '", "ids": ["Fn", "Semi", "Quote"], "grupo": "tecla",
     "funcao": "Home / End", "rainbow": "talvez"},
    {"teclas": "Fn + . / /", "ids": ["Fn", "Dot", "Slash"], "grupo": "tecla",
     "funcao": "Page Up / Page Down", "rainbow": "talvez"},
]
