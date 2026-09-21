// Renderiza quadros reais capturados (tools/serial-dump.py --save) em PNG com o
// MESMO colormap ironbow da página (engine.js), para conferir a primeira luz.
//   node tools/render-frames.cjs tools/fixtures/primeira-luz-0.1.1.bin saida.png [nQuadros] [escala]
const fs = require('fs'), path = require('path')
const { PNG } = require('pngjs')
require('../public/engine.js'); require('../public/serial-parser.js')
const { ironbow } = globalThis.Termica, { FrameParser } = globalThis.TermicaSerial

const [,, inFile, outFile = 'quadros.png', nMax = 8, scale = 10] = process.argv
const frames = [], lines = []
const p = new FrameParser(); p.onFrame = f => frames.push(f); p.onText = l => lines.push(l)
p.push(new Uint8Array(fs.readFileSync(inFile)))
if (!frames.length) { console.error('nenhum quadro válido em', inFile, '| texto:', lines.slice(0, 3)); process.exit(1) }
const sel = frames.slice(0, +nMax), W = 32, H = 24, S = +scale, pad = 6
const png = new PNG({ width: sel.length * (W * S + pad) + pad, height: H * S + 2 * pad })
png.data.fill(20)
// escala comum a todos os quadros (min/max globais), como o botão "escala fixa" da bancada
let lo = Infinity, hi = -Infinity
for (const f of sel) for (const v of f.t) { if (v < lo) lo = v; if (v > hi) hi = v }
sel.forEach((f, k) => {
  const ox = pad + k * (W * S + pad)
  for (let y = 0; y < H * S; y++) for (let x = 0; x < W * S; x++) {
    // bilinear entre os 32×24 píxeis, igual ao canvas com imageSmoothing
    const fx = Math.min(W - 1, Math.max(0, x / S - 0.5)), fy = Math.min(H - 1, Math.max(0, y / S - 0.5))
    const x0 = Math.floor(fx), y0 = Math.floor(fy), x1 = Math.min(W - 1, x0 + 1), y1 = Math.min(H - 1, y0 + 1), ax = fx - x0, ay = fy - y0
    const v = f.t[y0 * W + x0] * (1 - ax) * (1 - ay) + f.t[y0 * W + x1] * ax * (1 - ay) + f.t[y1 * W + x0] * (1 - ax) * ay + f.t[y1 * W + x1] * ax * ay
    const [r, g, b] = ironbow((v - lo) / Math.max(0.1, hi - lo))
    const i = ((pad + y) * png.width + ox + x) * 4
    png.data[i] = r; png.data[i + 1] = g; png.data[i + 2] = b; png.data[i + 3] = 255
  }
})
fs.writeFileSync(outFile, PNG.sync.write(png))
const st = sel.map(f => { let a = Infinity, b = -Infinity; for (const v of f.t) { if (v < a) a = v; if (v > b) b = v } return `seq ${f.seq}: ${a.toFixed(1)}–${b.toFixed(1)} °C Ta ${f.ta == null ? '—' : f.ta.toFixed(1)}` })
console.log(`${frames.length} quadros válidos em ${path.basename(inFile)} | texto: ${lines.join(' / ').slice(0, 160)}`)
console.log(st.join('\n')); console.log('escala', lo.toFixed(1), '→', hi.toFixed(1), '°C |', outFile)
