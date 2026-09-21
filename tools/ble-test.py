"""
SAFEBOAT TERMICA - teste do transporte Bluetooth LE (firmware 0.2.3+) a partir do PC.
Procura a placa "termica-*", assina o fluxo, valida os quadros de 1546 B (mesmo formato
da USB) e confere que o comando H e RECUSADO pelo BLE (rede/hub so pela USB).

  python tools/ble-test.py            # 20 s
  python tools/ble-test.py -s 60
Nao envia W nem X: nenhuma credencial passa por aqui.
"""
import asyncio, argparse, time, struct
from bleak import BleakScanner, BleakClient

SVC  = "5afe0001-5445-524d-4943-410000000001"
DATA = "5afe0002-5445-524d-4943-410000000001"
CTRL = "5afe0003-5445-524d-4943-410000000001"
FRAME_LEN = 1546

class Parser:
    def __init__(self):
        self.buf = b""; self.text = b""; self.frames = 0; self.bad = 0; self.lost = 0; self.last = None
        self.lines = []; self.stats = None; self.notifs = 0; self.bytes = 0; self.maxn = 0
    def push(self, d):
        self.notifs += 1; self.bytes += len(d); self.maxn = max(self.maxn, len(d))
        if len(d) >= 5 and d[0] == 0xB1:            # 0.2.7+: B1 | tipo | id | pedaco | total | carga
            mid, idx, cnt = d[2], d[3], d[4]
            if idx == 0: self.mid, self.nxt, self.parts = mid, 0, []
            if getattr(self, "mid", None) != mid or idx != getattr(self, "nxt", -1): self.msgdrop = getattr(self, "msgdrop", 0) + 1; self.mid = None; return
            self.parts.append(d[5:]); self.nxt += 1
            if self.nxt < cnt: return
            d = b"".join(self.parts); self.mid = None
        self.buf += d; i = 0; b = self.buf
        while i < len(b):
            if b[i] == 0xA5 and i + 2 >= len(b) and (i + 1 >= len(b) or b[i+1] == 0x5A): break
            if b[i] == 0xA5 and i + 2 < len(b) and b[i+1] == 0x5A and b[i+2] == 0x01:
                if len(b) - i < FRAME_LEN: break
                fr = b[i:i+FRAME_LEN]
                if (sum(fr[:-2]) & 0xFFFF) == int.from_bytes(fr[-2:], "little"):
                    seq, ta = struct.unpack_from("<Hh", fr, 4)
                    t = struct.unpack_from("<768h", fr, 8)
                    if self.last is not None:
                        gap = (seq - self.last - 1) & 0xFFFF
                        if gap < 1000: self.lost += gap
                    self.last = seq; self.frames += 1
                    self.stats = (seq, ta / 100, min(t) / 100, max(t) / 100, sum(t) / 76800)
                    i += FRAME_LEN; continue
                self.bad += 1
            c = b[i]
            if c == 10:
                if self.text: self.lines.append(self.text.decode("ascii", "replace")); self.text = b""
            elif 32 <= c < 127: self.text += bytes([c])
            i += 1
        self.buf = b[i:]

async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("-s", type=float, default=20.0); a = ap.parse_args()
    print("procurando 'termica-*' por ate 15 s ...")
    dev = await BleakScanner.find_device_by_filter(lambda d, ad: (d.name or ad.local_name or "").startswith("termica") or SVC in [u.lower() for u in ad.service_uuids], timeout=15)
    if not dev: print("NAO ACHEI a placa anunciando (firmware 0.2.3 gravado? Bluetooth do PC ligado?)"); return
    print("achei:", dev.name, dev.address)
    p = Parser()
    async with BleakClient(dev, winrt={"use_cached_services": False}, timeout=20) as c:   # sem cache: o Windows guarda a tabela GATT antiga
        print("conectado | MTU", c.mtu_size)
        await c.start_notify(DATA, lambda _, d: p.push(bytes(d)))
        t0 = time.time()
        await c.write_gatt_char(CTRL, b"i", response=False)
        await asyncio.sleep(2)
        await c.write_gatt_char(CTRL, b"H\thttp://192.168.0.148:8097", response=False)   # deve ser RECUSADO
        shown = 0
        while time.time() - t0 < a.s:
            await asyncio.sleep(1)
            for l in p.lines[shown:]:
                if not l.startswith("#J"): print("  ", l)
            shown = len(p.lines)
        dt = time.time() - t0
        await c.stop_notify(DATA)
    js = [l for l in p.lines if l.startswith("#J")]
    if js: print("  ultimo estado:", js[-1][:400])
    print(f"\n{p.frames} quadros validos em {dt:.1f} s = {p.frames/dt:.2f} q/s | perdidos {p.lost} | somas ruins {p.bad} | "
          f"{p.notifs} notificacoes, maior {p.maxn} B, {p.bytes/dt/1024:.1f} kB/s")
    if p.stats: print("ultimo quadro: seq %d | Ta %.2f C | min %.2f | max %.2f | media %.2f" % p.stats)
    print("mensagens BLE descartadas na remontagem:", getattr(p, "msgdrop", 0))
    print("recusa do H pelo BLE:", "OK" if any("recusado" in l for l in p.lines) else "NAO VI a recusa")

asyncio.run(main())
