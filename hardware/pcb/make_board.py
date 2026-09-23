# -*- coding: utf-8 -*-
"""
SAFEBOAT TERMICA v1 — gerador da PCB (KiCad 10 / pcbnew), fase 1.
Placa QUADRADA 32 × 32 mm (cantos R2), 2 camadas, 1,6 mm, p/ o case cúbico (~36 × 36 × 30 mm externo).
Montagem COMPLETA na JLCPCB (Standard, dois lados): SMD + bornes no lado F (RÉ) e o sensor MLX90640
110° (TO-39, THT) no lado B (FRENTE, virado p/ a janela).

Roda com o Python do KiCad:
  "%LOCALAPPDATA%/Programs/KiCad/10.0/bin/python.exe" make_board.py

Circuito (netlist pino a pino abaixo):
  +12 V barco (J2 borne KF350 3,5 mm; fusível 1 A no cabo) -> F1 PPTC 0,5 A/60 V -> D1 TVS SMAJ26A (p/ GND)
    -> D2 SS34 (série, inversão) -> VIN -> U2 AP63203 (buck síncrono 3,8–32 V, 3,3 V fixo, 2 A; EN=VIN; FB=VOUT)
       C5 10 µ/50 V entrada · L1 4,7 µH SWPA4020S · C6/C7 2x22 µ saída · C8 100 n BST
  USB de bancada: J1 JST-PH 4 (5V D- D+ GND) -> D3 SS14 -> VIN (a placa liga só no USB)
  U1 ESP32-C3-MINI-1: GPIO8 SDA · GPIO9 SCL (+BOOT SW1) · GPIO10 LED · GPIO4 SENS_OFF
    GPIO0 VSENSE (VIN/11: R7 200k / R8 20k + C4) · GPIO18/19 USB · EN R1 10k + C1 1 µ + SW2 RST
  Sensor: U3 MLX90640ESF-BAA (110°x75°; TO-39: 1 SDA · 2 VDD · 3 GND · 4 SCL) alimentado por VDD_MLX =
    3V3 via Q1 SI2301 (PMOS ligado por padrão: R5 100k gate->GND; GPIO4 alto = sensor OFF)
    C2 100 n + C3 10 µ junto ao VDD; pull-ups R2/R3 2k2 p/ VDD_MLX

Coordenadas: origem no CENTRO da placa, x -> direita, y -> CIMA (conversão em P()).
Módulo no topo (antena p/ +y, rente à borda); sensor 9,5 mm abaixo do centro (a lente fica
descentrada na face da frente — o módulo de 16,6 mm não deixa o sensor no centro de uma placa de 32).
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

W = H = 32.0
CR = 2.0
OX, OY = 100.0, 100.0
U1_Y = 7.65           # centro do módulo (topo em 15,95 = borda)
SENSOR_C = (0.0, -9.5)


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
board.GetDesignSettings().SetCopperLayerCount(2)

NET_NAMES = ["GND", "VIN_RAW", "VIN_F", "VIN", "3V3", "VDD_MLX", "SDA", "SCL", "EN", "LED_IO", "LED_A",
             "SENS_OFF", "GATE", "VBUS", "USB_DM", "USB_DP", "VSENSE", "SW", "BST"]
nets = {}
for n in NET_NAMES:
    ni = pcbnew.NETINFO_ITEM(board, n)
    board.Add(ni)
    nets[n] = ni


# ---------------------------------------------------------------- contorno: quadrado com cantos R2
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


hw, hh = W / 2, H / 2


def draw_outline(m=0.0):
    """contorno (recuado m mm — o DSN sai com recuo de 0,35 p/ o Freerouting respeitar o isolamento da borda)"""
    a, b, r = hw - m, hh - m, CR
    edge_seg(-a + r, b, a - r, b); edge_seg(-a + r, -b, a - r, -b)
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


def mlx90640_footprint(ref, x, y):
    """MLX90640 TO-39 (desenho mecânico do datasheet, rev. 12): pinos em círculo Ø5,84 a 45°, Ø0,45;
    flange Ø10,03; lata Ø9,30 (5,70 mm na versão 110°, 11,25 na 55°). Vista de BAIXO (pinos p/ o
    observador) com a aba p/ cima: SCL sup.-esq · SDA sup.-dir · GND inf.-esq · VDD inf.-dir
    (1 SDA · 2 VDD · 3 GND · 4 SCL). Definido como vista de cima e virado p/ o lado B (frente):
    no desenho da placa (vista da ré) a aba fica em +y e SDA em (+2,07; +2,07) — conferido."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("SAFEBOAT", "MLX90640_TO-39"))
    fp.SetReference(ref); fp.SetValue("MLX90640ESF-BAA")
    fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_THROUGH_HOLE)
    q = 5.84 / 2 * math.cos(math.radians(45))       # 2,065
    for nm, px, py in (("1", q, q), ("2", q, -q), ("3", -q, -q), ("4", -q, q)):
        _pth(fp, nm, px, py, 1.5, 0.8, pcbnew.PAD_SHAPE_RECT if nm == "1" else pcbnew.PAD_SHAPE_CIRCLE)
    _shape_circle(fp, pcbnew.F_SilkS, 5.15); _shape_circle(fp, pcbnew.F_Fab, 4.65, 0.1); _shape_circle(fp, pcbnew.F_CrtYd, 5.7, 0.05)
    _shape_rect(fp, pcbnew.F_SilkS, -0.4, 5.1, 0.4, 5.95)
    board.Add(fp); FPS[ref] = fp
    fp.SetLayerAndFlip(pcbnew.B_Cu)
    fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(0)


def kf350_footprint(ref, x, y):
    """Borne parafuso KF350-3.5-2P (LCSC C474892): passo 3,5 mm, pinos Ø1,0 (furo 1,3), corpo ~7,0 × 7,4 × 7,3 mm,
    entrada dos fios pelo lado -y (borda da placa)."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("SAFEBOAT", "KF350-3.5-2P"))
    fp.SetReference(ref); fp.SetValue("KF350-3.5-2P")
    fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_THROUGH_HOLE)
    _pth(fp, "1", -1.75, 0, 2.4, 1.3, pcbnew.PAD_SHAPE_RECT)
    _pth(fp, "2", 1.75, 0, 2.4, 1.3)
    _shape_rect(fp, pcbnew.F_SilkS, -3.6, -3.8, 3.6, 3.8)
    _shape_rect(fp, pcbnew.F_Fab, -3.5, -3.7, 3.5, 3.7, 0.1)
    _shape_rect(fp, pcbnew.F_CrtYd, -3.85, -4.05, 3.85, 4.05, 0.05)
    # marca da entrada dos fios (lado +y no frame = -y no projeto)
    _shape_rect(fp, pcbnew.F_SilkS, -2.9, 2.6, -0.6, 3.8, 0.2); _shape_rect(fp, pcbnew.F_SilkS, 0.6, 2.6, 2.9, 3.8, 0.2)
    board.Add(fp); FPS[ref] = fp
    fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(0)


R, C, C8_, C12 = ("Resistor_SMD", "R_0603_1608Metric"), ("Capacitor_SMD", "C_0603_1608Metric"), \
                 ("Capacitor_SMD", "C_0805_2012Metric"), ("Capacitor_SMD", "C_1210_3225Metric")

# =============================================================== PLACEMENT (y p/ cima)
mlx90640_footprint("U3", *SENSOR_C)                                    # lado B (frente)
place("U1", "Espressif", "ESP32-C3-MINI-1", 0.0, U1_Y, 0, "ESP32-C3-MINI-1-N4")
# --- faixa esquerda: buck
place("L1", "Inductor_SMD", "L_Sunlord_SWPA4020S", -11.4, 13.3, 0, "4.7u SWPA4020S")
place("U2", "Package_TO_SOT_SMD", "TSOT-23-6", -12.8, 8.9, 0, "AP63203WU-7")
place("C8", *C, -8.8, 8.9, 90, "100n")
place("C5", *C12, -12.8, 5.0, 0, "10u/50V")
place("C6", *C8_, -8.6, 5.0, 90, "22u")
place("C7", *C8_, -8.6, 1.2, 90, "22u")
place("C10", *C, -11.6, 1.2, 90, "100n")
place("C9", *C8_, -14.0, 1.2, 90, "10u")
# --- faixa direita: botões, EN, LED, chave do sensor
place("SW2", "Button_Switch_SMD", "SW_Push_1P1T_NO_CK_KMR2", 11.6, 13.8, 0, "RST")
place("SW1", "Button_Switch_SMD", "SW_Push_1P1T_NO_CK_KMR2", 11.6, 9.7, 0, "BOOT")
place("LED1", "LED_SMD", "LED_0603_1608Metric", 8.0, 5.6, 90, "LED")
place("R4", *R, 9.9, 5.6, 90, "1k")
place("R1", *R, 11.8, 5.6, 90, "10k")
place("C1", *C, 13.7, 5.6, 90, "1u")
place("Q1", "Package_TO_SOT_SMD", "SOT-23", 13.5, 1.6, 0, "SI2301")
place("R5", *R, 8.0, 1.6, 90, "100k")
place("R6", *R, 9.9, 1.6, 90, "1k")
# --- faixa inferior esquerda: entrada 12 V
kf350_footprint("J2", -11.6, -11.5)
place("F1", "Fuse", "Fuse_1812_4532Metric", -11.6, -4.2, 0, "PPTC 0.5A 60V")
place("D1", "Diode_SMD", "D_SMA", -4.4, -3.2, 0, "SMAJ26A")
place("D2", "Diode_SMD", "D_SMA", -5.6, -11.0, 90, "SS34")
# --- sob o sensor: desacoplamento
place("C2", *C, -1.7, -14.5, 0, "100n")
place("C3", *C, 1.7, -14.5, 0, "10u")
# --- faixa inferior direita: USB + leitura de VIN + pull-ups
place("J1", "Connector_JST", "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical", 6.0, -3.3, 0, "USB 5V D- D+ GND")
place("D3", "Diode_SMD", "D_SMA", 7.5, -9.0, 0, "SS14")
place("R2", *R, 4.5, -13.0, 90, "2k2")
place("R3", *R, 6.4, -13.0, 90, "2k2")
place("R7", *R, 8.3, -13.0, 90, "200k")
place("R8", *R, 10.2, -13.0, 90, "20k")
place("C4", *C, 12.1, -13.0, 90, "100n")

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
# sensor: TO-39 1 SDA 2 VDD 3 GND 4 SCL
net_pad("U3", 1, "SDA"); net_pad("U3", 2, "VDD_MLX"); net_pad("U3", 3, "GND"); net_pad("U3", 4, "SCL")
for r_ in ("C2", "C3"):
    net_pad(r_, 1, "VDD_MLX"); net_pad(r_, 2, "GND")
net_pad("R2", 1, "VDD_MLX"); net_pad("R2", 2, "SDA"); net_pad("R3", 1, "VDD_MLX"); net_pad("R3", 2, "SCL")
# chave do sensor — SOT-23 Q_PMOS_GSD: 1 G, 2 S, 3 D
net_pad("Q1", 1, "GATE"); net_pad("Q1", 2, "3V3"); net_pad("Q1", 3, "VDD_MLX")
net_pad("R5", 1, "GATE"); net_pad("R5", 2, "GND"); net_pad("R6", 1, "SENS_OFF"); net_pad("R6", 2, "GATE")
# entrada 12 V: J2 -> F1 -> VIN_F (TVS) -> D2 -> VIN
net_pad("J2", 1, "VIN_RAW"); net_pad("J2", 2, "GND")
net_pad("F1", 1, "VIN_RAW"); net_pad("F1", 2, "VIN_F")
net_pad("D1", 1, "VIN_F"); net_pad("D1", 2, "GND")          # 1 = K, 2 = A
net_pad("D2", 2, "VIN_F"); net_pad("D2", 1, "VIN")
net_pad("D3", 2, "VBUS"); net_pad("D3", 1, "VIN")
# buck AP63203 TSOT26: 1 FB 2 EN 3 VIN 4 GND 5 SW 6 BST
for num, nn in {1: "3V3", 2: "VIN", 3: "VIN", 4: "GND", 5: "SW", 6: "BST"}.items():
    net_pad("U2", num, nn)
net_pad("C5", 1, "VIN"); net_pad("C5", 2, "GND")
net_pad("C8", 1, "SW"); net_pad("C8", 2, "BST")
net_pad("L1", 1, "SW"); net_pad("L1", 2, "3V3")
for r_ in ("C6", "C7"):
    net_pad(r_, 1, "3V3"); net_pad(r_, 2, "GND")
net_pad("R7", 1, "VIN"); net_pad("R7", 2, "VSENSE"); net_pad("R8", 1, "VSENSE"); net_pad("R8", 2, "GND")
net_pad("C4", 1, "VSENSE"); net_pad("C4", 2, "GND")
# USB J1: 1 VBUS 2 D- 3 D+ 4 GND
net_pad("J1", 1, "VBUS"); net_pad("J1", 2, "USB_DM"); net_pad("J1", 3, "USB_DP"); net_pad("J1", 4, "GND")

for ref, fp in FPS.items():
    fp.Reference().SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
# módulo: sem courtyard/zonas embutidas; poda serigrafia fora da placa; keepout próprio da antena
for item in list(FPS["U1"].GraphicalItems()):
    if item.GetLayer() in (pcbnew.F_CrtYd, pcbnew.Dwgs_User, pcbnew.Cmts_User):
        FPS["U1"].Remove(item); continue
    if item.GetLayer() == pcbnew.F_SilkS:
        bb = item.GetBoundingBox()
        if OY - pcbnew.ToMM(bb.GetTop()) > hh - 0.3:
            FPS["U1"].Remove(item)
for _z in list(FPS["U1"].Zones()):
    FPS["U1"].Remove(_z)
_u1 = FPS["U1"].GetPosition()
for (x1, y1, x2, y2) in [(-6.65, -8.35, 6.65, -8.35), (6.65, -8.35, 6.65, 8.35), (6.65, 8.35, -6.65, 8.35), (-6.65, 8.35, -6.65, -8.35)]:
    _cy = pcbnew.PCB_SHAPE(FPS["U1"]); _cy.SetShape(pcbnew.SHAPE_T_SEGMENT)
    _cy.SetStart(VECTOR2I(_u1.x + FromMM(x1), _u1.y + FromMM(y1))); _cy.SetEnd(VECTOR2I(_u1.x + FromMM(x2), _u1.y + FromMM(y2)))
    _cy.SetLayer(pcbnew.F_CrtYd); _cy.SetWidth(FromMM(0.05)); FPS["U1"].Add(_cy)

# ---------------------------------------------------------------- regras + keepout antena
try:
    ns = board.GetDesignSettings().m_NetSettings
    dflt = ns.GetDefaultNetclass()
    dflt.SetTrackWidth(FromMM(0.25)); dflt.SetClearance(FromMM(0.15))
    dflt.SetViaDiameter(FromMM(0.6)); dflt.SetViaDrill(FromMM(0.3))
except Exception as e:
    print("netclass:", e)
board.GetDesignSettings().m_CopperEdgeClearance = FromMM(0.3)

ANT_Y = U1_Y + 2.9   # início da antena (y de projeto)
z = pcbnew.ZONE(board)
z.SetIsRuleArea(True)
z.SetDoNotAllowZoneFills(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowTracks(True)
z.SetDoNotAllowPads(False)
ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
z.SetLayerSet(ls)
sq = pcbnew.VECTOR_VECTOR2I()
for x, y in [(-6.6, ANT_Y), (6.6, ANT_Y), (6.6, hh + 1), (-6.6, hh + 1)]:
    sq.append(P(x, y))
z.AddPolygon(sq); board.Add(z)


def zone_outline(m):
    r2 = CR + 0.0
    pts = []
    for (cx, cy, a0) in [(hw - CR, hh - CR, 0), (-hw + CR, hh - CR, 90), (-hw + CR, -hh + CR, 180), (hw - CR, -hh + CR, 270)]:
        for k in range(7):
            a = math.radians(a0 + 90 * k / 6.0)
            pts.append((cx + (r2 - m) * math.cos(a), cy + (r2 - m) * math.sin(a)))
    return pts


def gnd_zone(layer):
    zz = pcbnew.ZONE(board)
    zz.SetLayer(layer); zz.SetNet(nets["GND"])
    zz.SetLocalClearance(FromMM(0.25)); zz.SetMinThickness(FromMM(0.2))
    zz.SetPadConnection(pcbnew.ZONE_CONNECTION_NONE if layer == pcbnew.F_Cu else pcbnew.ZONE_CONNECTION_THERMAL)
    try:
        zz.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    except Exception:
        pass
    poly = pcbnew.VECTOR_VECTOR2I()
    for x, y in zone_outline(0.4):
        poly.append(P(x, y))
    zz.AddPolygon(poly); board.Add(zz)


for _fp in board.GetFootprints():
    for _pd in _fp.Pads():
        if _pd.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            _pd.SetLocalClearance(FromMM(0.3))
for _pd in pad("J2", 2):
    _pd.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
gnd_zone(pcbnew.B_Cu)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(BOARD_PATH, board)
ok = pcbnew.ExportSpecctraDSN(board, DSN_PATH)      # com o contorno recuado
clear_outline(); draw_outline(0.0)                     # contorno real p/ a placa
gnd_zone(pcbnew.F_Cu)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(BOARD_PATH, board)
open(os.path.join(OUT_DIR, "kicad", "dnp.txt"), "w").write("\n".join(sorted(DNP)))
_p3 = [(p_.GetName(), round(pcbnew.ToMM(p_.GetPosition().x) - OX, 2), round(OY - pcbnew.ToMM(p_.GetPosition().y), 2)) for p_ in FPS["U3"].Pads()]
print("fase 1 ok:", BOARD_PATH, "| footprints:", len(FPS), "| DNP:", sorted(DNP), "| DSN:", ok, "| pinos do sensor:", _p3)
