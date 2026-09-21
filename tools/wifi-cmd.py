"""
SAFEBOAT TERMICA - envia um comando de linha ao firmware 0.2+ e mostra so o TEXTO
(linhas "# ..." e "#J {...}"), ignorando os quadros binarios.

  python tools/wifi-cmd.py COM26 S            # procurar redes 2,4 GHz
  python tools/wifi-cmd.py COM26 T -s 12      # batimento + sonda agora, escuta 12 s
  python tools/wifi-cmd.py COM26 "H\thttp://192.168.0.148:8097"
  python tools/wifi-cmd.py COM26 ""           # so escutar

NAO use este script para o comando W: a senha do Wi-Fi e digitada pelo usuario
na Bancada (navegador -> placa pela USB) e nao passa por terminal nem por log.
Abrir a porta REINICIA a placa (DTR): o banner aparece primeiro.
"""
import sys, time, argparse
import serial

FRAME_LEN = 1546

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port"); ap.add_argument("cmd")
    ap.add_argument("-s", type=float, default=9.0, help="segundos escutando apos o comando")
    ap.add_argument("-w", type=float, default=2.5, help="espera apos abrir a porta (boot da placa)")
    ap.add_argument("--teste-transporte", action="store_true", help="envia uma credencial FICTICIA de 10 caracteres para conferir que o comando W chega inteiro (sobrescreve a rede gravada)")
    ap.add_argument("--hub", help="grava o hub de teste (monta 'H<TAB>url' aqui dentro: o Git Bash troca \\t por /t nos argumentos)")
    a = ap.parse_args()
    if a.cmd[:1] in ("W", "w"):
        sys.exit("recusado: a senha do Wi-Fi e digitada pelo usuario na Bancada, nao aqui")
    cmd = ("H\t" + a.hub) if a.hub else a.cmd.replace("\\t", "\t")
    if a.teste_transporte:
        # credencial FICTICIA (rede que nao existe): so confere que o comando W chega inteiro a placa
        cmd = "W\tteste-transporte\tabcdefghij"

    s = serial.Serial(a.port, 115200, timeout=0.1)
    buf, text, frames, sent, t0 = b"", b"", 0, False, time.time()
    try:
        while True:
            el = time.time() - t0
            if not sent and el >= a.w:
                if cmd: s.write((cmd + "\n").encode()); print(">> enviado:", repr(cmd))
                sent = True; t_sent = time.time()
            if sent and time.time() - t_sent >= a.s: break
            buf += s.read(4096)
            i = 0
            while i < len(buf):
                if buf[i] == 0xA5 and i + 2 < len(buf) and buf[i+1] == 0x5A and buf[i+2] == 0x01:
                    if len(buf) - i < FRAME_LEN: break
                    fr = buf[i:i+FRAME_LEN]
                    if (sum(fr[:-2]) & 0xFFFF) == int.from_bytes(fr[-2:], "little"):
                        frames += 1; i += FRAME_LEN; continue
                c = buf[i]
                if c == 10:
                    if text: print("  " + text.decode("ascii", "replace")); text = b""
                elif 32 <= c < 127: text += bytes([c])
                i += 1
            buf = buf[i:]
    finally:
        s.close()
    print(f"({frames} quadros termicos validos recebidos nesse intervalo)")

if __name__ == "__main__":
    main()
