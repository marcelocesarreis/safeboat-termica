// Teste do parser do protocolo USB: quadros fatiados em pedaços arbitrários,
// texto intercalado, sync falso dentro do texto e perda de sequência.
require('../public/serial-parser.js')
const { FrameParser, encodeFrame, FRAME_LEN } = globalThis.TermicaSerial
const assert = require('assert')

const temps = new Float32Array(768).map((_, i) => 20 + (i % 32) * 0.5 + Math.floor(i / 32) * 0.25)
const f1 = encodeFrame(temps, 7, 25.31), f2 = encodeFrame(temps, 8, 25.32), f4 = encodeFrame(temps, 10, 25.35)
const txt = s => new Uint8Array(Buffer.from(s, 'ascii'))
// fluxo: banner, quadro 7, texto com sync falso (A5 5A 01 sem checksum), quadros 8 e 10 (9 perdido)
const parts = [txt('# SAFEBOAT Termica termica-usb 0.1.0\n'), f1, txt('# info '), new Uint8Array([0xA5, 0x5A, 0x01, 0x20]), txt('falso\n'), f2, f4]
const stream = Buffer.concat(parts.map(p => Buffer.from(p)))

const frames = [], lines = []
const p = new FrameParser()
p.onFrame = f => frames.push(f); p.onText = l => lines.push(l)
// alimenta em pedaços de tamanho pseudo-aleatório (1..700 bytes)
let seed = 42, i = 0
while (i < stream.length) { seed = (seed * 1103515245 + 12345) & 0x7fffffff; const n = 1 + (seed % 700); p.push(new Uint8Array(stream.subarray(i, i + n))); i += n }

assert.strictEqual(frames.length, 3, 'deveria decodificar 3 quadros')
assert.deepStrictEqual(frames.map(f => f.seq), [7, 8, 10])
assert.ok(Math.abs(frames[0].ta - 25.31) < 1e-6, 'Ta')
assert.ok(Math.abs(frames[0].t[33] - temps[33]) < 0.006, 'temperatura do pixel 33')
assert.strictEqual(frames[0].sensorOk, true)
assert.strictEqual(p.stats.lost, 1, 'um quadro perdido (seq 9)')
assert.strictEqual(p.stats.bad, 1, 'um sync falso rejeitado')
assert.deepStrictEqual(lines, ['# SAFEBOAT Termica termica-usb 0.1.0', '# info Z falso'])
// reset da placa no meio da sessao: seq volta a 0 -> nao conta como perda, conta como reset
const p2 = new FrameParser(); const got2 = [], txt2 = []
p2.onFrame = f => got2.push(f.seq); p2.onText = l => txt2.push(l)
for (const sq of [500, 501, 0, 1, 2]) p2.push(encodeFrame(temps, sq, 25))
assert.deepStrictEqual(got2, [500, 501, 0, 1, 2])
assert.strictEqual(p2.stats.lost, 0, 'reset nao e perda')
assert.strictEqual(p2.stats.resets, 1, 'um reset detectado')
assert.ok(txt2[0].includes('reiniciou'), 'avisa o reset no console')
console.log('reset da placa OK:', got2.join(','), '| perdidos', p2.stats.lost, '| resets', p2.stats.resets)
// bytes REAIS da placa (termica-usb 0.1.1, 17/09/2026): 10 quadros, banner, 0 perdidos
const fsx = require('fs'), fix = __dirname + '/fixtures/primeira-luz-0.1.1.bin'
if (fsx.existsSync(fix)) {
  const p3 = new FrameParser(); const fr3 = [], tx3 = []
  p3.onFrame = f => fr3.push(f); p3.onText = l => tx3.push(l)
  const raw = new Uint8Array(fsx.readFileSync(fix))
  for (let i = 0; i < raw.length; i += 333) p3.push(raw.subarray(i, i + 333))   // pedaços que nao alinham com o quadro
  assert.strictEqual(fr3.length, 10, 'fixture real: 10 quadros')
  assert.deepStrictEqual(fr3.map(f => f.seq), [0,1,2,3,4,5,6,7,8,9])
  assert.ok(fr3.every(f => f.sensorOk && !f.i2cErr), 'sensor OK em todos')
  assert.ok(fr3.every(f => f.ta > 29 && f.ta < 32), 'Ta ~30.9 C')
  assert.ok(fr3.every(f => Math.min(...f.t) > 20 && Math.max(...f.t) < 40), 'cena ambiente 26-31 C')
  assert.strictEqual(p3.stats.lost + p3.stats.bad + p3.stats.resets, 0)
  assert.ok(tx3[0].startsWith('# SAFEBOAT Termica termica-usb 0.1.1') && tx3[0].includes('MLX90640 @0x33 OK'), 'banner real')
  console.log('bytes reais OK:', fr3.length, 'quadros | Ta', fr3[0].ta, '| banner:', tx3[0].slice(0, 60) + '…')
}
// linha longa: o estado "#J {json}" do firmware 0.2 tem ~330 caracteres e tem de chegar inteiro
const p4 = new FrameParser(); const tx4 = []
p4.onText = l => tx4.push(l)
const longa = '#J ' + JSON.stringify({ dev: 'termica-7590', wifi: 'ok', ssid: 'Rede Com Espaco', enchimento: 'x'.repeat(400) })
p4.push(txt(longa + '\n')); p4.push(encodeFrame(temps, 1, 25)); p4.push(txt('# depois\n'))
assert.strictEqual(tx4[0], longa, 'linha longa intacta'); assert.strictEqual(JSON.parse(tx4[0].slice(3)).ssid, 'Rede Com Espaco')
assert.strictEqual(tx4[1], '# depois')
console.log('linha longa OK:', tx4[0].length, 'caracteres')
console.log('parser OK:', frames.length, 'quadros,', lines.length, 'linhas, perdidos', p.stats.lost, ', sync falso', p.stats.bad, ', FRAME_LEN', FRAME_LEN)

// fatias do tamanho do BLE (20, 244, 509 B) e de 1 B: o cabeçalho cai na fronteira e nenhum quadro pode sumir
{
  const real = require('fs').readFileSync(require('path').join(__dirname, 'fixtures', 'primeira-luz-0.1.1.bin'))
  for (const step of [1, 20, 244, 509]) {
    const p = new FrameParser(); let n = 0; p.onFrame = () => n++
    for (let o = 0; o < real.length; o += step) p.push(new Uint8Array(real.subarray(o, o + step)))
    if (n !== 10 || p.stats.bad || p.stats.lost) { console.error('FALHOU fatias de', step, 'B:', n, 'quadros', p.stats); process.exit(1) }
  }
  console.log('fatias BLE OK: 10 quadros com blocos de 1, 20, 244 e 509 B')
}
