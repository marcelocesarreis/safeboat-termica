"""
SAFEBOAT TERMICA - leitor de bancada da camera pela USB (protocolo termica-usb)

  python tools/serial-dump.py COM26            # mostra estatisticas por quadro
  python tools/serial-dump.py COM26 -n 20      # para apos 20 quadros
  python tools/serial-dump.py COM26 --save q.bin --ascii   # grava bytes crus + mapa ASCII

Mesmo protocolo de public/serial-parser.js (1546 bytes/quadro, checksum u16).
Abrir a porta RESETA a placa (DTR): o banner "# ..." aparece primeiro.
"""
import sys, time, struct, argparse
import serial

W, H, N = 32, 24, 768
HDR, FRAME_LEN = 8, 8 + 768 * 2 + 2
RAMP = " .:-=+*#%@"

def parse(buf):
    """devolve (quadros, linhas_de_texto, resto)"""
    frames, lines, text, i = [], [], b"", 0
    while i < len(buf):
        if buf[i] == 0xA5 and i + 2 < len(buf) and buf[i+1] == 0x5A and buf[i+2] == 0x01:
            if len(buf) - i < FRAME_LEN:
                break
            fr = buf[i:i+FRAME_LEN]
            if (sum(fr[:-2]) & 0xFFFF) == struct.unpack_from("<H", fr, FRAME_LEN-2)[0]:
                flags, seq, ta = struct.unpack_from("<BHh", fr, 3)
                t = [v/100 for v in struct.unpack_from("<768h", fr, HDR)]
                frames.append((seq, flags, None if ta == 0x7FFF else ta/100, t))
                i += FRAME_LEN
                continue
        c = buf[i]
        if c == 10:
            if text: lines.append(text.decode("ascii", "replace")); text = b""
        elif 32 <= c < 127:
            text += bytes([c])
        i += 1
    return frames, lines, buf[i:]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("-n", type=int, default=0, help="parar apos N quadros")
    ap.add_argument("--save", help="gravar bytes crus recebidos neste arquivo")
    ap.add_argument("--ascii", action="store_true", help="imprimir o mapa termico em ASCII")
    ap.add_argument("--rate", help="enviar comando de taxa (1/2/4/8) apos o banner")
    a = ap.parse_args()

    s = serial.Serial(a.port, 115200, timeout=0.2)
    raw = open(a.save, "wb") if a.save else None
    buf, got, last_seq, lost, t0 = b"", 0, None, 0, time.time()
    sent_rate = False
    print(f"aberto {a.port} - aguardando banner/quadros (Ctrl+C para sair)")
    try:
        while True:
            chunk = s.read(4096)
            if not chunk:
                continue
            if raw: raw.write(chunk)
            buf += chunk
            frames, lines, buf = parse(buf)
            for ln in lines:
                print("  " + ln)
                if a.rate and not sent_rate:
                    s.write(a.rate.encode()); sent_rate = True
            for seq, flags, ta, t in frames:
                got += 1
                if last_seq is not None:
                    d = (seq - last_seq) & 0xFFFF
                    if d > 1: lost += d - 1
                last_seq = seq
                lo, hi, avg = min(t), max(t), sum(t)/N
                imax = t.index(hi)
                fps = got / max(1e-6, time.time() - t0)
                print(f"q{seq:5d} flags={flags:02x} Ta={ta if ta is None else f'{ta:5.2f}'} "
                      f"min={lo:6.2f} max={hi:6.2f} med={avg:6.2f} pico=({imax%W},{imax//W}) "
                      f"fps={fps:4.1f} perdidos={lost}")
                if a.ascii:
                    for y in range(H):
                        row = t[y*W:(y+1)*W]
                        print("   " + "".join(RAMP[min(9, int((v-lo)/max(0.1, hi-lo)*9.999))] for v in row))
                if a.n and got >= a.n:
                    return
    except KeyboardInterrupt:
        pass
    finally:
        s.close()
        if raw: raw.close()
        print(f"\n{got} quadros, {lost} perdidos")

if __name__ == "__main__":
    main()
