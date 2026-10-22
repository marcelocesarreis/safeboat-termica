// Passa quadros REAIS gravados (tools/usb-ws-bridge.py --gravar) pelo classificador do estande e resume o que ele viu.
//   node tools/replay-expo.cjs tools/fixtures/arquivo.bin [--flipH]
const fs = require('fs')
require('../public/serial-parser.js'); require('../public/expo-ai.js')
const { FrameParser } = globalThis.TermicaSerial, { ExpoAI } = globalThis.TermicaExpo
const ai = new ExpoAI(), p = new FrameParser(), cnt = {}; const ppl = {}; let n = 0, smooth = null, withObj = 0, amb = 0, mx = -1e9
p.onFrame = fr => {
  if (!smooth) smooth = Float32Array.from(fr.t); else for (let i = 0; i < 768; i++) { const d = fr.t[i] - smooth[i]; smooth[i] += d * (Math.abs(d) > 4 ? 1 : 0.55) }
  const r = ai.process(smooth, n / 8); n++; amb = r.amb; if (r.hottest > mx) mx = r.hottest
  if (r.objects.length) withObj++
  ppl[r.people] = (ppl[r.people] || 0) + 1
  for (const o of r.objects) cnt[o.kind] = (cnt[o.kind] || 0) + 1
}
p.push(new Uint8Array(fs.readFileSync(process.argv[2])))
console.log(`${n} quadros (${(n / 8).toFixed(0)} s) | com detecção: ${withObj} (${(100 * withObj / Math.max(1, n)).toFixed(1)} %) | ambiente ${amb.toFixed(1)} °C | máx ${mx.toFixed(1)} °C`)
console.log(cnt, '| quadros por nº de pessoas:', ppl)
