# Créditos e licenças

## Bibliotecas incluídas

| Item | Versão | Origem | Licença |
|---|---|---|---|
| three.js (`three.module.min.js` + `three.core.min.js`) | 0.186.1 (r186) | cdnjs: `https://cdnjs.cloudflare.com/ajax/libs/three.js/0.186.1/` | MIT, texto em `alienware-command-center-linux/assets/vendor/three/LICENSE` (copiado de `mrdoob/three.js`, tag r186) |

O cdnjs não publica os exemplos do three.js (OrbitControls, EffectComposer, RoomEnvironment). Por isso os
controles de câmera (`alienware-command-center-linux/assets/3d/js/controles.js`), o bloom (`bloom.js`) e o ambiente de estúdio (em
`principal.js`) foram escritos para este projeto.

## Modelos 3D: o que foi procurado (29/10/2026)

Regra: só usar se desse para **baixar sem login** e se a licença permitisse **redistribuir num repositório
público** (CC0, CC-BY ou MIT), com crédito aqui.

| Fonte | O que achei | Decisão |
|---|---|---|
| Sketchfab, busca "AW720M" e tag `alienware` | Nenhum AW720M nem AW725H. Só o "Mouse Alienware AW610M" (palomadelapaz, https://sketchfab.com/3d-models/mouse-alienware-aw610m-113f69a482334bf3b5512893af2eb2fe) | Descartado: é outro mouse (AW610M), tem a marca **NoAI**, não está marcado como baixável e o Sketchfab exige login para baixar. |
| Printables, Thingiverse, GrabCAD (via STLFinder: https://www.stlfinder.com/3dmodels/alienware-case/) | Só gabinetes Alienware, suportes, ganchos de headset e peças de notebook | Descartado: nada do AW720M, do AW725H ou de teclado Alienware. |
| Galerias de IA (Meshy https://www.meshy.ai/tags/headphone, Tripo https://studio.tripo3d.ai/3d-model-gallery/headsets) | Headsets genéricos gerados por IA | Descartado: não são o AW725H e o Meshy pede conta para baixar. |
| Kenney "Computer Keyboard" (Poly Pizza https://poly.pizza/m/vsqTUPFSw6, Furniture Kit) | CC0, sem login, GLB | Licença serviria, mas foi descartado: é uma malha única de 32 triângulos, sem teclas separadas (não dá RGB por tecla). |
| Innerscene "75% mechanical keyboard - without case" (https://www.innerscene.com/tools/library/3d-parts/75-mechanical-keyboard-without-case-2f19f0a0) | CC0, GLB | Descartado: só o layout 75% e sem gabinete; não foi baixado. |
| Grab3D "Mechanical Keyboard" (https://grab3d.com/models/electronics/keyboard/) | CC0, sem login, TKL | Descartado: todas as teclas formam um objeto só e o estilo é pastel. |
| 3dassets.dev "Full-size keyboard" (https://3dassets.dev/assets/computers-and-desk-gadgets-keyboard-fullsize-096b61a4) | CC0, sem login | Descartado: feito por IA, grade genérica de 15×5 teclas, sem layout real. |
| Sketchfab "Mechanical Keyboard" (Flexryhe) e "Gaming RGB keyboard" (Zbrojmistrz) | Gratuitos | Descartados: exigem login; a licença do segundo não está clara. |
| BlendSwap "Mechanical keyboard 60%" (https://blendswap.com/blend/28909) | CC-BY | Descartado: só `.blend` (não há Blender na máquina para converter), pede login e é só 60%. |

**Resultado:** os três aparelhos são **procedurais**, escritos para este projeto em three.js
(`alienware-command-center-linux/assets/3d/js/modelos/mouse.js`, `headset.js`, `teclado.js`). Nenhum arquivo de modelo de terceiros foi
incluído.

## Referências usadas para modelar (só consulta, nada redistribuído)

- Dell, guia do usuário do AW720M (medidas de 125 × 62 × 37,5 mm; botões; DPI e LED de DPI na parte de
  baixo): https://gzhls.at/blob/ldb/7/9/c/c/e750eb0cbe600645278ae80f6a6152b0184b.pdf
- Dell, página do AW720M: https://www.dell.com/en-us/shop/gaming/apd/alienware-tri-mode-wireless-gaming-mouse-aw720m/ddpjk/-
- Gamingtrend (o único LED RGB é a cabeça de alienígena):
  https://gamingtrend.com/reviews/alienware-tri-mode-wireless-gaming-mouse-aw720m-built-to-last
- Ryan Yu, review em vídeo (dois botões laterais de cada lado, só o logo com RGB): https://www.youtube.com/watch?v=THouEzCwO9Y
- Dell, página do AW725H (arco de 45 mm com suspensão, almofadas de 95 mm, microfone retrátil, AlienFX RGB):
  https://www.dell.com/en-us/shop/gaming/apd/alienware-tri-mode-wireless-gaming-headset-aw725h/hpvk0/-
- Dell, guia do usuário do AW725H ("Alien head LED", medidas de 214 × 184 × 112 mm):
  https://gzhls.at/blob/ldb/c/e/5/f/2b98cece83796ccec39f1a3437f7a09c64fc.pdf
- Fotos de produto (Dell, Amazon, Ars Technica), vistas só como referência visual e não copiadas para cá.

## Marcas

"Alienware", "AlienFX", "Dark Side of the Moon", "Lunar Light" e a cabeça de alienígena são marcas da Dell.
A cabeça de alienígena dos modelos é um **desenho próprio aproximado** (curvas em `alienware-command-center-linux/assets/3d/js/comum.js`),
não o arquivo oficial do logo. Antes de publicar num repositório público, deixe claro que o projeto não é
oficial nem afiliado à Dell.
