// Controles próprios (o OrbitControls não vem no cdnjs):
//   arrastar na horizontal gira o aparelho (como num prato giratório),
//   arrastar na vertical inclina a câmera, a roda do mouse dá zoom,
//   duplo clique volta à vista inicial. Tudo com inércia suave.
import * as THREE from 'three';

export class Controles {
  constructor(elemento, camera, plataforma) {
    this.elemento = elemento;
    this.camera = camera;
    this.plataforma = plataforma;          // grupo que gira com o aparelho (yaw)
    this.alvo = new THREE.Vector3();       // ponto para onde a câmera olha
    this.inicial = { giro: -0.6, inclinacao: 0.38, distancia: 30 };
    this.giro = this.inicial.giro;         // rotação do aparelho (rad)
    this.inclinacao = this.inicial.inclinacao;  // elevação da câmera (rad)
    this.distancia = this.inicial.distancia;
    this.distanciaAlvo = this.distancia;
    this.velGiro = 0;
    this.velInclinacao = 0;
    this.girarSozinho = true;
    this.velocidadeAuto = 0.35;            // rad/s no giro automático
    this.arrastando = false;
    this.moveu = false;                    // distingue clique de arrasto
    this.voltando = null;                  // animação do duplo clique
    this.limites = { inclinacao: [0.02, 1.25], distancia: [10, 80] };

    elemento.addEventListener('pointerdown', (e) => this._descer(e));
    elemento.addEventListener('pointermove', (e) => this._mover(e));
    elemento.addEventListener('pointerup', (e) => this._subir(e));
    elemento.addEventListener('pointercancel', (e) => this._subir(e));
    elemento.addEventListener('wheel', (e) => this._roda(e), { passive: false });
    elemento.addEventListener('dblclick', () => this.resetar());
  }

  /** Ajusta a vista inicial para um aparelho de tamanho `tamanho` (Vector3, cm). */
  enquadrar(tamanho, alturaCentro, giro = -0.6, inclinacao = 0.38, zoom = 1) {
    this.tamanho = tamanho.clone();
    this.zoom = zoom;
    this.inicial = { giro, inclinacao, distancia: 0 };
    const d = this.distanciaPara();
    this.inicial.distancia = d;
    this.alvo.set(0, alturaCentro, 0);
    this.limites.distancia = [d * 0.45, d * 2.2];
    this.giro = giro;
    this.inclinacao = inclinacao;
    this.distancia = this.distanciaAlvo = d;
    this.velGiro = this.velInclinacao = 0;
    this.voltando = null;
  }

  /** Distância para o aparelho caber inteiro girando: a "pegada" (raio do prato giratório) tem de
   *  caber na largura e a altura aparente (vista de cima, inclinada) tem de caber na altura da tela. */
  distanciaPara() {
    const t = this.tamanho;
    const pegada = 0.5 * Math.hypot(t.x, t.z);
    const incl = this.inicial.inclinacao;
    const meiaAltura = 0.5 * (t.y * Math.cos(incl) + 2 * pegada * Math.sin(incl));
    const vertical = THREE.MathUtils.degToRad(this.camera.fov / 2);
    const horizontal = Math.atan(Math.tan(vertical) * this.camera.aspect);
    const d = Math.max(pegada / Math.tan(horizontal), meiaAltura / Math.tan(vertical)) * 1.08 + pegada * 0.6;
    return d * this.zoom;
  }

  /** Chamado quando a proporção da tela muda: mantém o aparelho inteiro à vista. */
  ajustarProporcao() {
    if (!this.tamanho) return;
    const nova = this.distanciaPara();
    const f = nova / this.inicial.distancia;
    this.inicial.distancia = nova;
    this.distancia *= f;
    this.distanciaAlvo *= f;
    this.limites.distancia = [nova * 0.45, nova * 2.2];
  }

  resetar() {
    // volta suavemente à vista inicial pelo caminho mais curto
    const volta = Math.PI * 2;
    let giro = this.inicial.giro;
    while (giro - this.giro > Math.PI) giro -= volta;
    while (giro - this.giro < -Math.PI) giro += volta;
    this.voltando = { de: { g: this.giro, i: this.inclinacao, d: this.distancia },
                      para: { g: giro, i: this.inicial.inclinacao, d: this.inicial.distancia }, t: 0 };
    this.velGiro = this.velInclinacao = 0;
    this.distanciaAlvo = this.inicial.distancia;
  }

  _descer(e) {
    if (e.button !== 0) return;
    this.arrastando = true;
    this.moveu = false;
    this.voltando = null;
    this.ultimo = { x: e.clientX, y: e.clientY, t: performance.now() };
    this.inicioToque = { x: e.clientX, y: e.clientY };
    this.elemento.setPointerCapture(e.pointerId);
    this.elemento.classList.add('arrastando');
  }

  _mover(e) {
    if (!this.arrastando) return;
    const dx = e.clientX - this.ultimo.x, dy = e.clientY - this.ultimo.y;
    if (Math.hypot(e.clientX - this.inicioToque.x, e.clientY - this.inicioToque.y) > 4) this.moveu = true;
    const agora = performance.now();
    const dt = Math.max(1, agora - this.ultimo.t) / 1000;
    const dg = dx * 0.009, di = dy * 0.006;
    this.giro += dg;
    this.inclinacao = THREE.MathUtils.clamp(this.inclinacao + di, ...this.limites.inclinacao);
    // velocidade média recente, usada na inércia depois de soltar
    this.velGiro = THREE.MathUtils.lerp(this.velGiro, dg / dt, 0.5);
    this.velInclinacao = THREE.MathUtils.lerp(this.velInclinacao, di / dt, 0.5);
    this.ultimo = { x: e.clientX, y: e.clientY, t: agora };
  }

  _subir(e) {
    if (!this.arrastando) return;
    this.arrastando = false;
    this.elemento.classList.remove('arrastando');
    if (this.elemento.hasPointerCapture(e.pointerId)) this.elemento.releasePointerCapture(e.pointerId);
    if (performance.now() - this.ultimo.t > 80) this.velGiro = this.velInclinacao = 0;  // soltou parado
  }

  _roda(e) {
    e.preventDefault();
    const fator = Math.exp(e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015));
    this.distanciaAlvo = THREE.MathUtils.clamp(this.distanciaAlvo * fator, ...this.limites.distancia);
  }

  /** Avança a animação (dt em segundos) e posiciona a câmera. */
  atualizar(dt) {
    if (this.voltando) {
      const v = this.voltando;
      v.t = Math.min(1, v.t + dt / 0.6);
      const s = v.t * v.t * (3 - 2 * v.t);  // suavização
      this.giro = THREE.MathUtils.lerp(v.de.g, v.para.g, s);
      this.inclinacao = THREE.MathUtils.lerp(v.de.i, v.para.i, s);
      this.distancia = THREE.MathUtils.lerp(v.de.d, v.para.d, s);
      if (v.t >= 1) this.voltando = null;
    } else if (!this.arrastando) {
      // inércia: a velocidade cai ~ 5% por quadro a 60 qps
      const atrito = Math.pow(0.05, dt);
      this.giro += this.velGiro * dt;
      this.inclinacao = THREE.MathUtils.clamp(this.inclinacao + this.velInclinacao * dt, ...this.limites.inclinacao);
      this.velGiro *= atrito;
      this.velInclinacao *= atrito;
      if (this.girarSozinho && Math.abs(this.velGiro) < 0.05) this.giro += this.velocidadeAuto * dt;
      this.distancia = THREE.MathUtils.lerp(this.distancia, this.distanciaAlvo, 1 - Math.pow(0.0001, dt));
    }
    this.aplicar();
  }

  aplicar() {
    this.plataforma.rotation.y = this.giro;
    const c = Math.cos(this.inclinacao), s = Math.sin(this.inclinacao);
    this.camera.position.set(this.alvo.x, this.alvo.y + this.distancia * s, this.alvo.z + this.distancia * c);
    this.camera.lookAt(this.alvo);
  }
}
