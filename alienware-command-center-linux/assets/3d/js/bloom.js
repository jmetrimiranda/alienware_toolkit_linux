// Pós-processamento próprio (o cdnjs não traz o EffectComposer dos exemplos do three.js):
//   1) a cena é desenhada num alvo HDR (meia precisão, MSAA 4x) com fundo transparente;
//   2) as partes mais claras que o limiar (zonas de luz emissivas) são borradas em 4 níveis;
//   3) a composição soma cena + brilho, aplica o tone mapping e a conversão sRGB do renderer
//      e pinta o fundo (gradiente radial nas cores do painel) onde a cena é transparente.
import * as THREE from 'three';

const VERTICE = /* glsl */`
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

// Passa só o que é mais claro que o limiar (com joelho suave, sem corte seco)
const CLAROS = /* glsl */`
  uniform sampler2D tMapa;
  uniform float limiar;
  varying vec2 vUv;
  void main() {
    vec3 c = texture2D(tMapa, vUv).rgb;
    float l = max(c.r, max(c.g, c.b));
    float peso = smoothstep(limiar, limiar * 1.6, l);
    gl_FragColor = vec4(c * peso, 1.0);
  }
`;

// Desfoque gaussiano de 9 amostras numa direção (horizontal ou vertical)
const DESFOQUE = /* glsl */`
  uniform sampler2D tMapa;
  uniform vec2 passo;
  varying vec2 vUv;
  void main() {
    vec3 s = texture2D(tMapa, vUv).rgb * 0.2270270;
    s += texture2D(tMapa, vUv + passo * 1.3846153).rgb * 0.3162162;
    s += texture2D(tMapa, vUv - passo * 1.3846153).rgb * 0.3162162;
    s += texture2D(tMapa, vUv + passo * 3.2307692).rgb * 0.0702703;
    s += texture2D(tMapa, vUv - passo * 3.2307692).rgb * 0.0702703;
    gl_FragColor = vec4(s, 1.0);
  }
`;

// Composição final (vai para a tela, então recebe o tone mapping e o sRGB do renderer)
const FINAL = /* glsl */`
  uniform sampler2D tCena, tB0, tB1, tB2, tB3;
  uniform float forca;
  uniform vec3 fundoCentro, fundoBorda;
  uniform vec2 proporcao;
  varying vec2 vUv;
  void main() {
    vec4 cena = texture2D(tCena, vUv);
    vec3 brilho = texture2D(tB0, vUv).rgb * 0.5 + texture2D(tB1, vUv).rgb * 0.8
                + texture2D(tB2, vUv).rgb * 1.0 + texture2D(tB3, vUv).rgb * 1.2;
    gl_FragColor = vec4(cena.rgb + brilho * forca, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
    // fundo: gradiente radial (já em sRGB) só onde não há objeto nem sombra
    vec2 p = (vUv - vec2(0.5, 0.56)) * proporcao;
    vec3 fundo = mix(fundoCentro, fundoBorda, smoothstep(0.05, 0.95, length(p)));
    gl_FragColor.rgb += fundo * (1.0 - cena.a);
    // ruído de 1/255 para não aparecer faixas no gradiente
    gl_FragColor.rgb += (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 255.0;
  }
`;

function alvo(samples = 0) {
  return new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples, depthBuffer: samples > 0 });
}

function srgb(hex) {
  // cor do fundo em sRGB (não em linear), porque entra depois da conversão de cor
  const c = new THREE.Color(hex);
  return new THREE.Vector3(...c.getRGB(new THREE.Color(), THREE.SRGBColorSpace).toArray());
}

export class Bloom {
  constructor(renderer, { forca = 0.55, limiar = 0.95 } = {}) {
    this.renderer = renderer;
    this.cena = alvo(4);
    this.niveis = [0, 1, 2, 3].map(() => ({ a: alvo(), b: alvo() }));
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2));
    this.quad.frustumCulled = false;
    this.cenaQuad = new THREE.Scene();
    this.cenaQuad.add(this.quad);

    const comum = { vertexShader: VERTICE, depthTest: false, depthWrite: false };
    this.matClaros = new THREE.ShaderMaterial({ ...comum, fragmentShader: CLAROS,
      uniforms: { tMapa: { value: null }, limiar: { value: limiar } }, toneMapped: false });
    this.matDesfoque = new THREE.ShaderMaterial({ ...comum, fragmentShader: DESFOQUE,
      uniforms: { tMapa: { value: null }, passo: { value: new THREE.Vector2() } }, toneMapped: false });
    this.matFinal = new THREE.ShaderMaterial({ ...comum, fragmentShader: FINAL,
      uniforms: {
        tCena: { value: this.cena.texture },
        tB0: { value: this.niveis[0].a.texture }, tB1: { value: this.niveis[1].a.texture },
        tB2: { value: this.niveis[2].a.texture }, tB3: { value: this.niveis[3].a.texture },
        forca: { value: forca },
        fundoCentro: { value: srgb('#24272c') }, fundoBorda: { value: srgb('#16181b') },
        proporcao: { value: new THREE.Vector2(1, 1) },
      } });
  }

  setSize(largura, altura) {
    // tamanhos em pixels reais do framebuffer
    this.cena.setSize(largura, altura);
    this.niveis.forEach((n, i) => {
      const w = Math.max(1, Math.round(largura / 2 ** (i + 1)));
      const h = Math.max(1, Math.round(altura / 2 ** (i + 1)));
      n.a.setSize(w, h);
      n.b.setSize(w, h);
    });
    const m = Math.max(largura, altura);
    this.matFinal.uniforms.proporcao.value.set(largura / m, altura / m);
  }

  _passar(material, destino) {
    this.quad.material = material;
    this.renderer.setRenderTarget(destino);
    this.renderer.render(this.cenaQuad, this.camera);
  }

  render(cena, camera) {
    const r = this.renderer;
    const corAntes = r.getClearColor(new THREE.Color());
    const alfaAntes = r.getClearAlpha();

    // 1) cena no alvo HDR com fundo transparente
    r.setRenderTarget(this.cena);
    r.setClearColor(0x000000, 0);
    r.clear();
    r.render(cena, camera);

    // 2) claros + desfoque em cascata (cada nível tem metade do tamanho do anterior)
    //    (horizontal: entrada -> b; vertical: b -> a; nunca lê e escreve a mesma textura)
    this.matClaros.uniforms.tMapa.value = this.cena.texture;
    this._passar(this.matClaros, this.niveis[0].a);
    let entrada = this.niveis[0].a.texture;
    for (const n of this.niveis) {
      this.matDesfoque.uniforms.tMapa.value = entrada;
      this.matDesfoque.uniforms.passo.value.set(1 / n.b.width, 0);
      this._passar(this.matDesfoque, n.b);
      this.matDesfoque.uniforms.tMapa.value = n.b.texture;
      this.matDesfoque.uniforms.passo.value.set(0, 1 / n.a.height);
      this._passar(this.matDesfoque, n.a);
      entrada = n.a.texture;
    }

    // 3) composição na tela
    this._passar(this.matFinal, null);
    r.setClearColor(corAntes, alfaAntes);
  }
}
