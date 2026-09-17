/**
 * SAFEBOAT TÉRMICA — protocolo USB da câmera (termica-usb) · parser + encoder
 *
 * Quadro binário (little-endian), 1546 bytes:
 *   0xA5 0x5A   sync
 *   u8  ver     = 1
 *   u8  flags   bit0 sensor OK · bit1 houve erro I²C neste quadro
 *   u16 seq     contador (detecta perda)
 *   i16 ta      temperatura ambiente do sensor ×100 (0x7FFF = indisponível)
 *   i16 t[768]  temperaturas ×100, linha a linha (32 colunas × 24 linhas)
 *   u16 sum     soma de todos os bytes anteriores, mod 65536
 *
 * Fora dos quadros a placa manda texto (linhas iniciadas por "# ") — o parser
 * separa os dois: um quadro só é aceito se sync + versão + checksum baterem.
 * Mesmo arquivo roda no navegador (Web Serial) e no Node (testes).
 */
;(function (global) {
  'use strict'
  const W = 32, H = 24, N = W * H
  const HDR = 8, FRAME_LEN = HDR + N * 2 + 2   // 1546
  const TA_NA = 0x7FFF

  class FrameParser {
    constructor () {
      this.buf = new Uint8Array(0)
      this.text = ''
      this.onFrame = null       // ({ t: Float32Array(768), seq, ta, flags, sensorOk, i2cErr })
      this.onText = null        // (linha)
      this.stats = { frames: 0, bad: 0, lost: 0, resets: 0, lastSeq: -1, bytes: 0 }
    }
    push (chunk) {
      this.stats.bytes += chunk.length
      const nb = new Uint8Array(this.buf.length + chunk.length)
      nb.set(this.buf); nb.set(chunk, this.buf.length)
      this.buf = nb
      let i = 0
      const b = this.buf
      while (i < b.length) {
        if (b[i] === 0xA5 && i + 2 < b.length && b[i + 1] === 0x5A && b[i + 2] === 0x01) {
          if (b.length - i < FRAME_LEN) break            // quadro incompleto: espera mais bytes
          if (this._sumOk(i)) { this._emit(i); i += FRAME_LEN; continue }
          this.stats.bad++                                // sync falso: trata como texto
        }
        const c = b[i]
        if (c === 10) { const line = this.text; this.text = ''; if (this.onText && line.length) this.onText(line) }
        else if (c >= 32 && c < 127) { this.text += String.fromCharCode(c); if (this.text.length > 240) this.text = this.text.slice(-240) }
        i++
      }
      this.buf = b.slice(i)
      if (this.buf.length > 65536) this.buf = this.buf.slice(-FRAME_LEN)   // nunca cresce sem limite
    }
    _sumOk (o) {
      let s = 0
      for (let k = 0; k < FRAME_LEN - 2; k++) s = (s + this.buf[o + k]) & 0xFFFF
      return s === (this.buf[o + FRAME_LEN - 2] | (this.buf[o + FRAME_LEN - 1] << 8))
    }
    _emit (o) {
      const dv = new DataView(this.buf.buffer, this.buf.byteOffset + o, FRAME_LEN)
      const flags = dv.getUint8(3), seq = dv.getUint16(4, true), taRaw = dv.getInt16(6, true)
      const t = new Float32Array(N)
      for (let k = 0; k < N; k++) t[k] = dv.getInt16(HDR + 2 * k, true) / 100
      if (this.stats.lastSeq >= 0) {
        const d = (seq - this.stats.lastSeq) & 0xFFFF
        if (d > 1 && d < 32768) this.stats.lost += d - 1        // salto p/ frente = quadros perdidos
        else if (d >= 32768) { this.stats.resets++; if (this.onText) this.onText('# parser: sequência voltou (' + this.stats.lastSeq + ' → ' + seq + ') — a placa reiniciou') }
      }
      this.stats.lastSeq = seq; this.stats.frames++
      if (this.onFrame) this.onFrame({ t, seq, flags, ta: taRaw === TA_NA ? null : taRaw / 100, sensorOk: !!(flags & 1), i2cErr: !!(flags & 2) })
    }
  }

  // monta um quadro binário a partir de floats (simulador e testes)
  function encodeFrame (temps, seq, ta, flags = 1) {
    const out = new Uint8Array(FRAME_LEN)
    const dv = new DataView(out.buffer)
    out[0] = 0xA5; out[1] = 0x5A; out[2] = 1; out[3] = flags & 0xFF
    dv.setUint16(4, seq & 0xFFFF, true)
    dv.setInt16(6, ta == null ? TA_NA : Math.round(ta * 100), true)
    for (let k = 0; k < N; k++) dv.setInt16(HDR + 2 * k, Math.max(-32768, Math.min(32767, Math.round(temps[k] * 100))), true)
    let s = 0
    for (let k = 0; k < FRAME_LEN - 2; k++) s = (s + out[k]) & 0xFFFF
    dv.setUint16(FRAME_LEN - 2, s, true)
    return out
  }

  global.TermicaSerial = { FrameParser, encodeFrame, FRAME_LEN, W, H }
})(typeof window !== 'undefined' ? window : globalThis)
