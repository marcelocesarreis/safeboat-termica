// Teste do classificador do estande contra o roteiro da DemoScene: cada trecho tem de produzir a classe esperada.
require('../public/expo-ai.js')
const { ExpoAI, DemoScene } = globalThis.TermicaExpo
const ai = new ExpoAI(), scene = new DemoScene()
const seen = {}          // segundo → conjunto de classes
for (let i = 0; i < 40 * 8; i++) {
  const t = i / 8, r = ai.process(scene.frame(t), t), s = Math.floor(t)
  seen[s] = seen[s] || { kinds: new Set(), people: 0, alert: false, amb: r.amb }
  r.objects.forEach(o => seen[s].kinds.add(o.kind)); seen[s].people = Math.max(seen[s].people, r.people); if (r.alert) seen[s].alert = true
}
let fail = 0
const expect = (s, cond, msg) => { const ok = cond(seen[s]); if (!ok) fail++; console.log((ok ? 'ok   ' : 'FALHA') + ` t=${s}s ${msg} → [${[...seen[s].kinds].join(', ')}] pessoas=${seen[s].people} alerta=${seen[s].alert} amb=${seen[s].amb.toFixed(1)}`) }
expect(1, r => r.kinds.size === 0, 'cena vazia: nada')
expect(8, r => r.kinds.has('pessoa') && r.people === 1, 'visitante: pessoa')
expect(13, r => r.kinds.has('pessoa') && r.kinds.has('quente') && !r.alert, 'visitante com café: pessoa + objeto quente, sem alerta')
expect(26, r => r.kinds.has('pessoa_longe') || r.kinds.has('pessoa'), 'pessoa ao fundo')
expect(28, r => r.kinds.has('frio'), 'lata gelada: objeto frio')
expect(38, r => r.alert && r.kinds.has('muito_quente'), 'ponto quente em rampa: alerta')
expect(39, r => !r.kinds.has('mao') && !r.kinds.has('pessoa'), 'halo do ponto quente não vira mão/pessoa')
console.log(fail ? `\n${fail} FALHA(S)` : '\ntudo certo')
process.exit(fail ? 1 : 0)
