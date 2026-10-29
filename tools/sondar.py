"""Ferramenta de linha de comando para descobrir o protocolo do AW720M.

Uso:
  python sondar.py escutar 60        # só escuta (seguro); salva em logs/
  python sondar.py extras 20         # só escuta os 5 bytes extras de cada movimento (seguro)
  python sondar.py gravar 90         # só escuta as duas interfaces juntas, com horário (seguro)
  python sondar.py guiado            # igual ao gravar, mas mostra o que fazer em cada fase (seguro)
  python sondar.py status            # EXPERIMENTAL: envia o comando de status do AW610M
  python sondar.py cor 255 0 0 [zona] [brilho]   # EXPERIMENTAL: muda a cor
"""

import os
import select
import sys
import time

# Os módulos de aparelho ficam na pasta do app (alienware-command-center-linux/)
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alienware-command-center-linux")
sys.path.insert(0, APP)
import aw720m  # noqa: E402

PASTA_LOGS = os.path.join(APP, "logs")  # mesmos logs do painel


def abrir():
    info = aw720m.achar()
    if info is None:
        sys.exit("AW720M não encontrado. Confira se o dongle está conectado e o mouse ligado.")
    try:
        mouse = aw720m.Mouse(info["caminho"])
    except aw720m.SemPermissao:
        sys.exit(f"Sem permissão em {info['caminho']}. Rode antes: sudo ./instalar_permissao.sh")
    print(f"Conectado: {info['modo']} em {info['caminho']}")
    return mouse


def salvar(nome, linhas):
    os.makedirs(PASTA_LOGS, exist_ok=True)
    arquivo = os.path.join(PASTA_LOGS, f"{nome}-{time.strftime('%Y%m%d-%H%M%S')}.txt")
    with open(arquivo, "w") as f:
        f.write("\n".join(linhas) + "\n")
    print(f"Salvo em {arquivo}")


FASES_GUIADAS = [
    (10, "Mãos fora (referência)"),
    (15, "Só MEXA o mouse, sem clicar"),
    (10, "Mãos fora"),
    (15, "CLIQUE ESQUERDO 3 vezes, sem mexer"),
    (15, "CLIQUE DIREITO 3 vezes, sem mexer"),
    (10, "Gire a RODA para cima e para baixo"),
    (15, "Botão de DPI 3 vezes, devagar, sem mexer"),
    (10, "Mãos fora"),
    (20, "ENCOSTE o carregador magnético e mexa devagar"),
    (20, "TIRE o carregador e mexa devagar"),
    (10, "Mãos fora"),
]


def gravar(fases):
    """Escuta a interface de fabricante e a do mouse ao mesmo tempo, com horário e fases.

    fases = lista de (segundos, instrução). Do mouse registra: mudança dos 5 bytes extras,
    mudança dos botões e, a cada 5 s, quantos relatórios e cliques de roda chegaram.
    """
    info = aw720m.achar()
    if info is None or "caminho_mouse" not in info:
        sys.exit("AW720M não encontrado.")
    try:
        fab = os.open(info["caminho"], os.O_RDONLY | os.O_NONBLOCK)
        mouse = os.open(info["caminho_mouse"], os.O_RDONLY | os.O_NONBLOCK)
    except PermissionError:
        sys.exit("Sem permissão. Rode antes: sudo ./instalar_permissao.sh")
    linhas = []
    extras_antes, botoes_antes, relatorios, roda, marca = None, 0, 0, 0, 5
    inicio = time.time()
    fim_fase = 0
    for numero, (duracao, texto) in enumerate(fases, 1):
        fim_fase += duracao
        aviso = f"Fase {numero}/{len(fases)} ({duracao} s): {texto}"
        print(f"\n>>> {aviso}", flush=True)
        linhas.append(f"{time.time() - inicio:6.2f}s ==== {aviso}")
        while True:
            t = time.time() - inicio
            if t >= marca:
                linhas.append(f"{marca:6.1f}s ---- {relatorios} relatório(s) do mouse, roda {roda:+d} nos últimos 5 s")
                relatorios, roda, marca = 0, 0, marca + 5
            if t >= fim_fase:
                break
            prontos, _, _ = select.select([fab, mouse], [], [], 0.2)
            for fd in prontos:
                dados = os.read(fd, aw720m.TAMANHO)
                t = time.time() - inicio
                if fd == fab:
                    linhas.append(f"{t:6.2f}s fab    {aw720m.hexa(dados)}")
                    continue
                relatorios += 1
                roda += int.from_bytes(dados[5:6], "little", signed=True)
                if dados[0] != botoes_antes:
                    linhas.append(f"{t:6.2f}s mouse  botões {dados[0]:08b}")
                    botoes_antes = dados[0]
                extras = dados[6:11]
                if extras != extras_antes:
                    linhas.append(f"{t:6.2f}s mouse  extras {' '.join(f'{b:02x}' for b in extras)}")
                    extras_antes = extras
            print(f"\r    faltam {max(0, fim_fase - (time.time() - inicio)):4.1f} s ", end="", flush=True)
    os.close(fab)
    os.close(mouse)
    print("\n\nFim.")
    salvar("gravacao", linhas)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    acao = sys.argv[1]

    if acao == "gravar":
        gravar([(float(sys.argv[2]) if len(sys.argv) > 2 else 90, "Gravação livre")])
        return

    if acao == "guiado":
        gravar(FASES_GUIADAS)
        return

    if acao == "extras":
        info = aw720m.achar()
        if info is None or "caminho_mouse" not in info:
            sys.exit("AW720M não encontrado.")
        segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 20
        print(f"Mexa o mouse por {segundos:.0f} s ({info['caminho_mouse']})...")
        try:
            contagem = aw720m.escutar_extras_do_mouse(info["caminho_mouse"], segundos)
        except aw720m.SemPermissao:
            sys.exit("Sem permissão. Rode antes: sudo ./instalar_permissao.sh")
        linhas = [f"{n:6d}x  {' '.join(f'{b:02x}' for b in extras)}" for extras, n in contagem.items()]
        print("\n".join(linhas) or "Nenhum movimento recebido.")
        salvar("extras", linhas)
        return

    mouse = abrir()

    if acao == "escutar":
        segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 30
        print(f"Escutando {segundos:.0f} s... mexa no mouse, aperte o botão de DPI, encoste o carregador.")
        quadros = mouse.escutar(segundos)
        inicio = quadros[0][0] if quadros else 0
        linhas = [f"+{t - inicio:7.2f}s  {aw720m.hexa(q)}" for t, q in quadros]
        print("\n".join(linhas) or "Nenhum quadro recebido na interface de fabricante.")
        salvar("escuta", linhas)

    elif acao == "status":
        respostas = mouse.status()
        linhas = [f"enviado:  {aw720m.hexa(aw720m.CMD_STATUS)}"]
        linhas += [f"resposta: {aw720m.hexa(r)}" for r in respostas] or ["resposta: nenhuma"]
        print("\n".join(linhas))
        salvar("status", linhas)

    elif acao == "cor":
        r, g, b = (int(x) for x in sys.argv[2:5])
        zona = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        brilho = int(sys.argv[6]) if len(sys.argv) > 6 else 100
        respostas = mouse.definir_cor(r, g, b, zona=zona, brilho=brilho)
        for resposta in respostas:
            print(f"resposta: {aw720m.hexa(resposta)}")
        print("Comando enviado. Veja se a cor do mouse mudou.")

    else:
        sys.exit(__doc__)
    mouse.fechar()


if __name__ == "__main__":
    main()
