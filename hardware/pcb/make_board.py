# -*- coding: utf-8 -*-
"""
SAFEBOAT TERMICA v2 — gerador da PCB (KiCad 10 / pcbnew), fase 1.
Rev. 2 (reunião de 22/10/2026): 4 camadas (In1 = plano GND, In2 = plano 3V3), placa 40 × 40 mm (cantos R2),
recortes laterais na antena, nada metálico ao lado da antena, 4 furos M2,5 longe da antena, roteador a 90°,
isolamento 0,2 mm (JLC ≥ 0,127), entrada 8–32 V com MP4560 (55 V) + SMBJ33A + capacitores de 100 V,
fio de alimentação soldado direto (pads P1/P2), PPTC mantido. Montagem completa JLCPCB (Standard, 2 lados):
SMD + JST no lado F (RÉ) e o sensor MLX90640 110° (TO-39, THT) no lado B (FRENTE).

Roda com o Python do KiCad:
  "%LOCALAPPDATA%/Programs/KiCad/10.0/bin/python.exe" make_board.py

Circuito (netlist pino a pino abaixo):
  +8–32 V barco (P1/P2, fio soldado; fusível 1 A no cabo) -> F1 PPTC 0,5 A/60 V -> D1 TVS SMBJ33A (p/ GND)
    -> D2 SS34 (série, inversão) -> VIN -> U2 MP4560 (buck 3,8–55 V, 2 A, 488 kHz: R11 200k no FREQ)
       C5/C11 2x4,7 µ/100 V entrada · L1 10 µH SWPA5040S · D4 SS36 (roda livre) · C6/C7 2x22 µ saída
       C8 100 n BST · FB: R9 47k / R10 15k (0,8 V ref -> 3,31 V) · COMP: R12 68k + C12 1 n · EN flutuante (liga)
  USB de bancada: J1 JST-PH 4 (5V D- D+ GND) -> D3 SS14 -> VIN
  U1 ESP32-C3-MINI-1: GPIO8 SDA · GPIO9 SCL (+BOOT SW1) · GPIO10 LED · GPIO4 SENS_OFF
    GPIO0 VSENSE (VIN/23: R7 330k / R8 15k + C4) · GPIO18/19 USB · EN R1 10k + C1 1 µ + SW2 RST
  Sensor: U3 MLX90640ESF-BAA (110°; TO-39: 1 SDA · 2 VDD · 3 GND · 4 SCL) em VDD_MLX = 3V3 via Q1 SI2301
    (PMOS ligado por padrão: R5 100k gate->GND; GPIO4 alto = sensor OFF); C2 100 n + C3 10 µ; pull-ups R2/R3 2k2

Coordenadas: origem no CENTRO da placa, x -> direita, y -> CIMA (conversão em P()).
"""
import os, re, math
import pcbnew
from pcbnew import FromMM, VECTOR2I

KICAD_SHARE = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\share\kicad")
FP_DIR = os.path.join(KICAD_SHARE, "footprints")
SYM_DIR = os.path.join(KICAD_SHARE, "symbols")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_LIB = os.path.join(OUT_DIR, "lib")
NAME = "safeboat-termica-v1"
BOARD_PATH = os.path.join(OUT_DIR, "kicad", NAME + ".kicad_pcb")
DSN_PATH = os.path.join(OUT_DIR, "kicad", NAME + ".dsn")
os.makedirs(os.path.dirname(BOARD_PATH), exist_ok=True)

W = H = 40.0
CR = 2.0
OX, OY = 100.0, 100.0
hw, hh = W / 2, H / 2
U1_Y = 11.65                     # centro do módulo: topo em 19,95 (borda 20)
ANT_Y = U1_Y + 2.9               # início da antena = 13,55
NOTCH_X0, NOTCH_X1 = 6.9, 10.2   # recortes laterais da antena (Espressif: "cut out both sides"); 0,3 além do módulo
NOTCH_Y = ANT_Y - 0.2            # 14,35
SENSOR_C = (0.0, -12.0)
HOLES = [(-17.5, 3.0), (17.5, 3.0), (-17.5, -18.0), (17.5, -18.0)]   # M2,5 (Ø2,7) — longe da antena
HOLE_D, HOLE_KEEP = 2.7, 2.3     # furo e raio livre p/ a cabeça do parafuso


def P(x, y):
    return VECTOR2I(FromMM(OX + x), FromMM(OY - y))


def parse_symbol_pins(libfile, symname):
    path = os.path.join(SYM_DIR, libfile)
    if not os.path.exists(path):
        path = os.path.join(LOCAL_LIB, libfile)
    txt = open(path, encoding="utf-8").read()
    m = re.search(r'\(symbol "%s"' % re.escape(symname), txt)
    depth, i, start = 0, m.start(), m.start()
    while i < len(txt):
        if txt[i] == '(':
            depth += 1
        elif txt[i] == ')':
            depth -= 1
            if depth == 0:
                break
        i += 1
    block = txt[start:i + 1]
    pins = {}
    for pm in re.finditer(r'\(pin\s+\w+\s+\w+[\s\S]*?\(name\s+"([^"]+)"[\s\S]*?\(number\s+"([^"]+)"', block):
        pins[pm.group(2)] = pm.group(1)
    return pins


board = pcbnew.NewBoard(BOARD_PATH)
board.GetDesignSettings().SetCopperLayerCount(4)

NET_NAMES = ["GND", "VIN_RAW", "VIN_F", "VIN", "3V3", "VDD_MLX", "SDA", "SCL", "EN", "LED_IO", "LED_A",
             "SENS_OFF", "GATE", "VBUS", "USB_DM", "USB_DP", "VSENSE", "SW", "BST", "FB", "COMP", "FREQ"]
nets = {}
for n in NET_NAMES:
    ni = pcbnew.NETINFO_ITEM(board, n)
    board.Add(ni)
    nets[n] = ni


# ---------------------------------------------------------------- contorno: quadrado R2 com recortes na antena
def edge_seg(x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(x1, y1)); s.SetEnd(P(x2, y2))
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FromMM(0.1))
    board.Add(s)


def edge_arc(cx, cy, r, a0, a1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    am = math.radians((a0 + a1) / 2.0); aa = math.radians(a0); ab = math.radians(a1)
    s.SetArcGeometry(P(cx + r * math.cos(aa), cy + r * math.sin(aa)),
                     P(cx + r * math.cos(am), cy + r * math.sin(am)),
                     P(cx + r * math.cos(ab), cy + r * math.sin(ab)))
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FromMM(0.1))
    board.Add(s)


def draw_outline(m=0.0):
    """contorno recuado m mm (o DSN sai com 0,35 p/ o Freerouting respeitar o isolamento da borda).
    Topo: borda — recorte esquerdo — língua do módulo — recorte direito — borda."""
    a, b, r = hw - m, hh - m, CR
    x0, x1, yn = NOTCH_X0 - m, NOTCH_X1 + m, NOTCH_Y - m
    # topo com os dois recortes
    edge_seg(-a + r, b, -x1, b); edge_seg(-x1, b, -x1, yn); edge_seg(-x1, yn, -x0, yn); edge_seg(-x0, yn, -x0, b)
    edge_seg(-x0, b, x0, b)
    edge_seg(x0, b, x0, yn); edge_seg(x0, yn, x1, yn); edge_seg(x1, yn, x1, b); edge_seg(x1, b, a - r, b)
    edge_seg(-a + r, -b, a - r, -b)
    edge_seg(-a, b - r, -a, -b + r); edge_seg(a, b - r, a, -b + r)
    edge_arc(a - r, b - r, r, 0, 90); edge_arc(-a + r, b - r, r, 90, 180)
    edge_arc(-a + r, -b + r, r, 180, 270); edge_arc(a - r, -b + r, r, 270, 360)


def clear_outline():
    for d in [d_ for d_ in board.GetDrawings() if d_.GetLayer() == pcbnew.Edge_Cuts]:
        board.Remove(d)


draw_outline(0.35)


def load_fp(lib, name):
    d = os.path.join(FP_DIR, lib + ".pretty")
    if not os.path.exists(d):
        d = os.path.join(LOCAL_LIB, lib + ".pretty")
    fp = pcbnew.FootprintLoad(d, name)
    if fp is None:
        raise RuntimeError("footprint %s:%s nao achado" % (lib, name))
    return fp


FPS = {}
DNP = set()


def place(ref, lib, name, x, y, rot=0, value="", dnp=False, back=False):
    fp = load_fp(lib, name)
    fp.SetReference(ref); fp.SetValue(value or ref)
    board.Add(fp); FPS[ref] = fp
    if back:
        fp.SetLayerAndFlip(pcbnew.B_Cu)
    fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(rot)
    if dnp:
        DNP.add(ref)
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_DNP)
    return fp


def pad(ref, padname):
    out = [p_ for p_ in FPS[ref].Pads() if p_.GetName() == str(padname)]
    if not out:
        raise RuntimeError("pad %s em %s nao achado" % (padname, ref))
    return out


def net_pad(ref, padname, netname):
    for p_ in pad(ref, padname):
        p_.SetNet(nets[netname])


BOARD_ONLY = pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES


def _pth(fp, nm, px, py, size, drill, shape=pcbnew.PAD_SHAPE_CIRCLE):
    p = pcbnew.PAD(fp)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetShape(shape)
    p.SetSize(VECTOR2I(FromMM(size), FromMM(size)))
    p.SetDrillSize(VECTOR2I(FromMM(drill), FromMM(drill)))
    p.SetLayerSet(pcbnew.PAD.PTHMask())
    p.SetPosition(VECTOR2I(FromMM(px), FromMM(py)))
    p.SetName(nm); fp.Add(p)


def _shape_circle(fp, layer, rr, w=0.12):
    c = pcbnew.PCB_SHAPE(fp); c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetCenter(VECTOR2I(0, 0)); c.SetEnd(VECTOR2I(FromMM(rr), 0)); c.SetLayer(layer); c.SetWidth(FromMM(w)); fp.Add(c)


def _shape_rect(fp, layer, x0, y0, x1, y1, w=0.12):
    t = pcbnew.PCB_SHAPE(fp); t.SetShape(pcbnew.SHAPE_T_RECT)
    t.SetStart(VECTOR2I(FromMM(x0), FromMM(y0))); t.SetEnd(VECTOR2I(FromMM(x1), FromMM(y1)))
    t.SetLayer(layer); t.SetWidth(FromMM(w)); fp.Add(t)


def _model(fp, fname):
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = "${KIPRJMOD}/../lib/3d/" + fname
    m.m_Show = True
    fp.Models().push_back(m)


def wire_pad(ref, value, x, y, drill=1.3, size=2.6, square=False):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("SAFEBOAT", "WirePad_%s" % ref))
    fp.SetReference(ref); fp.SetValue(value)
    _pth(fp, "1", 0, 0, size, drill, pcbnew.PAD_SHAPE_RECT if square else pcbnew.PAD_SHAPE_CIRCLE)
    _shape_circle(fp, pcbnew.F_CrtYd, size / 2 + 0.25, 0.05)
    fp.SetAttributes(fp.GetAttributes() | BOARD_ONLY)
    board.Add(fp); FPS[ref] = fp
    fp.SetPosition(P(x, y))


def mount_hole(ref, x, y):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("SAFEBOAT", "MountHole_M2.5_NPTH"))
    fp.SetReference(ref); fp.SetValue("M2.5")
    p = pcbnew.PAD(fp)
    p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(VECTOR2I(FromMM(HOLE_D), FromMM(HOLE_D))); p.SetDrillSize(VECTOR2I(FromMM(HOLE_D), FromMM(HOLE_D)))
    p.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
    fp.Add(p)
    _shape_circle(fp, pcbnew.F_CrtYd, HOLE_KEEP, 0.05); _shape_circle(fp, pcbnew.B_CrtYd, HOLE_KEEP, 0.05)
    _shape_circle(fp, pcbnew.F_SilkS, HOLE_D / 2 + 0.4, 0.12)
    fp.SetAttributes(fp.GetAttributes() | BOARD_ONLY)
    board.Add(fp); FPS[ref] = fp
    fp.SetPosition(P(x, y))


def mlx90640_footprint(ref, x, y):
    """MLX90640 TO-39 (datasheet rev. 12): pinos em círculo Ø5,84 a 45°, flange Ø10,03, lata Ø9,30 (5,70 na versão
    110°). Vista de baixo com a aba p/ cima: SCL sup.-esq · SDA sup.-dir · GND inf.-esq · VDD inf.-dir
    (1 SDA · 2 VDD · 3 GND · 4 SCL). Definido como vista de cima e virado p/ o lado B (frente) — conferido."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("SAFEBOAT", "MLX90640_TO-39"))
    fp.SetReference(ref); fp.SetValue("MLX90640ESF-BAA")
    fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_THROUGH_HOLE)
    q = 5.84 / 2 * math.cos(math.radians(45))
    for nm, px, py in (("1", q, q), ("2", q, -q), ("3", -q, -q), ("4", -q, q)):
        _pth(fp, nm, px, py, 1.5, 0.8, pcbnew.PAD_SHAPE_RECT if nm == "1" else pcbnew.PAD_SHAPE_CIRCLE)
    _shape_circle(fp, pcbnew.F_SilkS, 4.95); _shape_circle(fp, pcbnew.F_Fab, 4.65, 0.1); _shape_circle(fp, pcbnew.F_CrtYd, 5.7, 0.05)
    _shape_rect(fp, pcbnew.F_SilkS, -0.4, 4.9, 0.4, 5.75)
    _model(fp, "MLX90640_TO-39-110.wrl")
    board.Add(fp); FPS[ref] = fp
    fp.SetLayerAndFlip(pcbnew.B_Cu)
    fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(0)


R, C, C8_, C12 = ("Resistor_SMD", "R_0603_1608Metric"), ("Capacitor_SMD", "C_0603_1608Metric"), \
                 ("Capacitor_SMD", "C_0805_2012Metric"), ("Capacitor_SMD", "C_1210_3225Metric")

# =============================================================== PLACEMENT (y p/ cima)
mlx90640_footprint("U3", *SENSOR_C)                                    # lado B (frente)
place("U1", "Espressif", "ESP32-C3-MINI-1", 0.0, U1_Y, 0, "ESP32-C3-MINI-1-N4")
for i, (hx, hy) in enumerate(HOLES):
    mount_hole("H%d" % (i + 1), hx, hy)
# --- faixa esquerda do módulo (só passivos pequenos): desacoplo, EN, chave do sensor
place("C10", *C, -8.0, 11.3, 90, "100n")
place("C9", *C8_, -8.0, 7.8, 90, "10u")
place("R1", *R, -10.3, 11.3, 90, "10k")
place("C1", *C, -12.3, 11.3, 90, "1u")
place("Q1", "Package_TO_SOT_SMD", "SOT-23", -11.2, 7.8, 0, "SI2301")
place("R5", *R, -10.3, 4.2, 90, "100k")
place("R6", *R, -8.3, 4.2, 90, "1k")
# --- faixa direita do módulo (só passivos): LED, pull-ups, leitura de VIN
place("LED1", "LED_SMD", "LED_0603_1608Metric", 8.0, 11.3, 90, "LED")
place("R4", *R, 9.9, 11.3, 90, "1k")
place("R2", *R, 8.0, 7.8, 90, "2k2")
place("R3", *R, 9.9, 7.8, 90, "2k2")
place("R7", *R, 11.8, 7.8, 90, "330k")
place("R8", *R, 8.0, 4.2, 90, "15k")
place("C4", *C, 9.9, 4.2, 90, "100n")
# --- inferior esquerda: USB, botões, entrada 8–32 V
place("J1", "Connector_JST", "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical", -14.0, -2.0, 0, "USB 5V D- D+ GND")
place("D3", "Diode_SMD", "D_SMA", -3.4, -3.5, 90, "SS14")
place("SW1", "Button_Switch_SMD", "SW_Push_1P1T_NO_CK_KMR2", -16.0, -7.5, 0, "BOOT")
place("SW2", "Button_Switch_SMD", "SW_Push_1P1T_NO_CK_KMR2", -9.5, -7.5, 0, "RST")
place("D2", "Diode_SMD", "D_SMA", -13.8, -13.0, 90, "SS34")
place("D1", "Diode_SMD", "D_SMB", -7.8, -12.8, 0, "SMBJ33A")
place("F1", "Fuse", "Fuse_1812_4532Metric", -8.9, -17.4, 0, "PPTC 0.5A 60V")
wire_pad("P1", "+VIN 8-32V", -4.1, -17.6, square=True)
wire_pad("P2", "GND", 7.4, -14.1)
# --- sob/ao lado do sensor: desacoplo (lado F)
place("C2", *C, 3.2, -16.8, 90, "100n")
place("C3", *C, 4.9, -16.8, 90, "10u")
# --- inferior direita: buck MP4560 (SOIC-8 EP: 1 SW 2 EN 3 COMP 4 FB 5 GND 6 FREQ 7 VIN 8 BST)
place("U2", "Package_SO", "HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm", 11.0, -3.0, 0, "MP4560DN")
place("C6", *C8_, 5.2, -4.5, 90, "22u")
place("C7", *C8_, 5.2, -0.8, 90, "22u")
place("L1", "Inductor_SMD", "L_Sunlord_SWPA5040S", 6.5, -9.5, 0, "10u SWPA5040S")
place("C8", *C, 11.3, -7.2, 0, "100n")
place("C5", *C12, 17.0, -3.0, 90, "4.7u/100V")
place("C11", *C12, 17.0, -8.0, 90, "4.7u/100V")
place("R11", *R, 14.0, -9.0, 90, "200k")
place("C12", *C, 10.3, -13.0, 90, "1n")
place("R10", *R, 12.3, -13.0, 90, "15k")
place("R9", *R, 14.3, -13.0, 90, "47k")
place("R12", *R, 16.3, -13.0, 90, "68k")
place("D4", "Diode_SMD", "D_SMA", 11.0, -17.6, 0, "SS36")

# =============================================================== NETLIST
esp = parse_symbol_pins("Espressif.kicad_sym", "ESP32-C3-MINI-1")
by_name = {}
for num, name in esp.items():
    by_name.setdefault(name.upper(), []).append(num)


def esp_nums(io_name):
    key = io_name.upper()
    out = list(by_name.get(key, []))
    if not out:
        for k, v in by_name.items():
            if k.split("/")[0] == key:
                out += v
    if not out:
        raise RuntimeError("pino %s nao achado no simbolo" % io_name)
    return out


def esp_net(io_name, netname):
    for num in esp_nums(io_name):
        net_pad("U1", num, netname)


esp_net("GND", "GND"); esp_net("3V3", "3V3"); esp_net("EN", "EN")
esp_net("GPIO8", "SDA"); esp_net("GPIO9", "SCL"); esp_net("GPIO10", "LED_IO"); esp_net("GPIO4", "SENS_OFF")
esp_net("GPIO0", "VSENSE"); esp_net("GPIO18", "USB_DM"); esp_net("GPIO19", "USB_DP")
for r_ in ("C9", "C10"):
    net_pad(r_, 1, "3V3"); net_pad(r_, 2, "GND")
net_pad("R1", 1, "3V3"); net_pad("R1", 2, "EN"); net_pad("C1", 1, "EN"); net_pad("C1", 2, "GND")
net_pad("SW2", 1, "EN"); net_pad("SW2", 2, "GND")
net_pad("SW1", 1, "SCL"); net_pad("SW1", 2, "GND")
net_pad("R4", 1, "LED_IO"); net_pad("R4", 2, "LED_A"); net_pad("LED1", 2, "LED_A"); net_pad("LED1", 1, "GND")
net_pad("U3", 1, "SDA"); net_pad("U3", 2, "VDD_MLX"); net_pad("U3", 3, "GND"); net_pad("U3", 4, "SCL")
for r_ in ("C2", "C3"):
    net_pad(r_, 1, "VDD_MLX"); net_pad(r_, 2, "GND")
net_pad("R2", 1, "VDD_MLX"); net_pad("R2", 2, "SDA"); net_pad("R3", 1, "VDD_MLX"); net_pad("R3", 2, "SCL")
net_pad("Q1", 1, "GATE"); net_pad("Q1", 2, "3V3"); net_pad("Q1", 3, "VDD_MLX")
net_pad("R5", 1, "GATE"); net_pad("R5", 2, "GND"); net_pad("R6", 1, "SENS_OFF"); net_pad("R6", 2, "GATE")
# entrada: P1 -> F1 -> VIN_F (TVS) -> D2 -> VIN
net_pad("P1", 1, "VIN_RAW"); net_pad("P2", 1, "GND")
net_pad("F1", 1, "VIN_RAW"); net_pad("F1", 2, "VIN_F")
net_pad("D1", 1, "VIN_F"); net_pad("D1", 2, "GND")          # 1 = K, 2 = A
net_pad("D2", 2, "VIN_F"); net_pad("D2", 1, "VIN")
net_pad("D3", 2, "VBUS"); net_pad("D3", 1, "VIN")
# buck MP4560 SOIC8E: 1 SW 2 EN 3 COMP 4 FB 5 GND 6 FREQ 7 VIN 8 BST 9 EP(GND); EN flutua (habilita)
for num, nn in {1: "SW", 3: "COMP", 4: "FB", 5: "GND", 6: "FREQ", 7: "VIN", 8: "BST", 9: "GND"}.items():
    net_pad("U2", num, nn)
net_pad("C5", 1, "VIN"); net_pad("C5", 2, "GND"); net_pad("C11", 1, "VIN"); net_pad("C11", 2, "GND")
net_pad("C8", 1, "SW"); net_pad("C8", 2, "BST")
net_pad("L1", 1, "SW"); net_pad("L1", 2, "3V3")
net_pad("D4", 2, "GND"); net_pad("D4", 1, "SW")            # roda livre: anodo GND, catodo SW
for r_ in ("C6", "C7"):
    net_pad(r_, 1, "3V3"); net_pad(r_, 2, "GND")
net_pad("R9", 1, "3V3"); net_pad("R9", 2, "FB"); net_pad("R10", 1, "FB"); net_pad("R10", 2, "GND")
net_pad("R12", 1, "COMP"); net_pad("R12", 2, "COMP_C")if False else None
nets["COMP_C"] = pcbnew.NETINFO_ITEM(board, "COMP_C"); board.Add(nets["COMP_C"])
net_pad("R12", 1, "COMP"); net_pad("R12", 2, "COMP_C"); net_pad("C12", 1, "COMP_C"); net_pad("C12", 2, "GND")
net_pad("R11", 1, "FREQ"); net_pad("R11", 2, "GND")
net_pad("R7", 1, "VIN"); net_pad("R7", 2, "VSENSE"); net_pad("R8", 1, "VSENSE"); net_pad("R8", 2, "GND")
net_pad("C4", 1, "VSENSE"); net_pad("C4", 2, "GND")
net_pad("J1", 1, "VBUS"); net_pad("J1", 2, "USB_DM"); net_pad("J1", 3, "USB_DP"); net_pad("J1", 4, "GND")

for ref, fp in FPS.items():
    fp.Reference().SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
# módulo: sem courtyard/zonas embutidas; poda serigrafia fora da placa; keepout próprio da antena
for item in list(FPS["U1"].GraphicalItems()):
    if item.GetLayer() in (pcbnew.F_CrtYd, pcbnew.Dwgs_User, pcbnew.Cmts_User):
        FPS["U1"].Remove(item); continue
    if item.GetLayer() == pcbnew.F_SilkS:
        bb = item.GetBoundingBox()
        if OY - pcbnew.ToMM(bb.GetTop()) > NOTCH_Y - 0.5:     # serigrafia da área da antena cairia nos recortes
            FPS["U1"].Remove(item)
for _z in list(FPS["U1"].Zones()):
    FPS["U1"].Remove(_z)
_u1 = FPS["U1"].GetPosition()
for (x1, y1, x2, y2) in [(-6.65, -8.35, 6.65, -8.35), (6.65, -8.35, 6.65, 8.35), (6.65, 8.35, -6.65, 8.35), (-6.65, 8.35, -6.65, -8.35)]:
    _cy = pcbnew.PCB_SHAPE(FPS["U1"]); _cy.SetShape(pcbnew.SHAPE_T_SEGMENT)
    _cy.SetStart(VECTOR2I(_u1.x + FromMM(x1), _u1.y + FromMM(y1))); _cy.SetEnd(VECTOR2I(_u1.x + FromMM(x2), _u1.y + FromMM(y2)))
    _cy.SetLayer(pcbnew.F_CrtYd); _cy.SetWidth(FromMM(0.05)); FPS["U1"].Add(_cy)

# ---------------------------------------------------------------- regras (JLC: isolamento >= 0,127; usamos 0,2)
try:
    ns = board.GetDesignSettings().m_NetSettings
    dflt = ns.GetDefaultNetclass()
    dflt.SetTrackWidth(FromMM(0.25)); dflt.SetClearance(FromMM(0.2))
    dflt.SetViaDiameter(FromMM(0.6)); dflt.SetViaDrill(FromMM(0.3))
except Exception as e:
    print("netclass:", e)
board.GetDesignSettings().m_CopperEdgeClearance = FromMM(0.3)

ALL_CU = pcbnew.LSET()
for _l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
    ALL_CU.AddLayer(_l)
# keepout da antena + recortes: sem cobre nas 4 camadas em |x| <= 9,9, y >= 13,35
z = pcbnew.ZONE(board)
z.SetIsRuleArea(True)
z.SetDoNotAllowZoneFills(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowTracks(True)
z.SetDoNotAllowPads(False)
z.SetLayerSet(ALL_CU)
sq = pcbnew.VECTOR_VECTOR2I()
for x, y in [(-NOTCH_X1 - 0.3, NOTCH_Y), (NOTCH_X1 + 0.3, NOTCH_Y), (NOTCH_X1 + 0.3, hh + 1), (-NOTCH_X1 - 0.3, hh + 1)]:
    sq.append(P(x, y))
z.AddPolygon(sq); board.Add(z)
# vias térmicas do EP do MP4560 (GND) ANTES do roteamento: o Freerouting as vê como obstáculo/ligação
for _vx, _vy in ((10.55, -3.6), (11.45, -3.6), (10.55, -2.4), (11.45, -2.4)):
    _v = pcbnew.PCB_VIA(board)
    _v.SetPosition(P(_vx, _vy)); _v.SetDrill(FromMM(0.3)); _v.SetWidth(FromMM(0.6))
    _v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); _v.SetNet(nets["GND"]); board.Add(_v)


def fill_zone(layer, netname, m=0.4, pad_conn=pcbnew.ZONE_CONNECTION_THERMAL, prio=0):
    zz = pcbnew.ZONE(board)
    zz.SetLayer(layer); zz.SetNet(nets[netname])
    zz.SetLocalClearance(FromMM(0.25)); zz.SetMinThickness(FromMM(0.2))
    zz.SetPadConnection(pad_conn)
    zz.SetAssignedPriority(prio)
    try:
        zz.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    except Exception:
        pass
    poly = pcbnew.VECTOR_VECTOR2I()
    for x, y in [(-hw + m, -hh + m), (hw - m, -hh + m), (hw - m, hh - m), (-hw + m, hh - m)]:
        poly.append(P(x, y))
    zz.AddPolygon(poly); board.Add(zz)
    return zz


for _fp in board.GetFootprints():
    for _pd in _fp.Pads():
        if _pd.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            _pd.SetLocalClearance(FromMM(0.5))
for _pd in pad("P2", 1):
    _pd.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
# O roteador só vê F e B (DSN exportado como placa de 2 camadas, plano GND em B): assim as camadas internas
# ficam SÓ com os planos sólidos (In1 GND, In2 3V3), sem trilhas cortando-os. As vias passantes das redes
# GND/3V3 ligam-se aos planos automaticamente no KiCad.
fill_zone(pcbnew.B_Cu, "GND", pad_conn=pcbnew.ZONE_CONNECTION_THERMAL)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.GetDesignSettings().SetCopperLayerCount(2)
pcbnew.SaveBoard(BOARD_PATH, board)
ok = pcbnew.ExportSpecctraDSN(board, DSN_PATH)      # com o contorno recuado, 2 camadas
board.GetDesignSettings().SetCopperLayerCount(4)
fill_zone(pcbnew.In1_Cu, "GND", pad_conn=pcbnew.ZONE_CONNECTION_THERMAL)
fill_zone(pcbnew.In2_Cu, "3V3", pad_conn=pcbnew.ZONE_CONNECTION_THERMAL)
# DSN: 90 graus e planos internos como "power" (o Freerouting não roteia neles, só fura p/ eles)
_d = open(DSN_PATH, encoding="utf-8").read()
_d = _d.replace("(structure", "(structure\n    (snap_angle ninety_degree)", 1)
# In1/In2 ficam como 'signal' no DSN: com 'power' o Freerouting nao conecta os pads aos planos; os planos
# exportados como (plane ...) ja bloqueiam qualquer outra rede nessas camadas.
open(DSN_PATH, "w", encoding="utf-8").write(_d)
clear_outline(); draw_outline(0.0)                     # contorno real p/ a placa
fill_zone(pcbnew.F_Cu, "GND", pad_conn=pcbnew.ZONE_CONNECTION_THERMAL)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(BOARD_PATH, board)
open(os.path.join(OUT_DIR, "kicad", "dnp.txt"), "w").write("\n".join(sorted(DNP)))
_p3 = [(p_.GetName(), round(pcbnew.ToMM(p_.GetPosition().x) - OX, 2), round(OY - pcbnew.ToMM(p_.GetPosition().y), 2)) for p_ in FPS["U3"].Pads()]
print("fase 1 ok:", BOARD_PATH, "| footprints:", len(FPS), "| DSN:", ok, "| pinos do sensor:", _p3)
