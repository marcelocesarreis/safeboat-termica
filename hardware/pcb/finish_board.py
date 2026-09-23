# -*- coding: utf-8 -*-
"""
SAFEBOAT TERMICA v1 — fase 2: importa o SES do Freerouting, alarga potência, costura e união dos
planos de GND, serigrafia (ré) + rótulos do sensor (frente) + logo, .kicad_pro (regras de DRC
vivem no PROJETO). Receita herdada do AIR-NODE / VIB.

  "%LOCALAPPDATA%/Programs/KiCad/10.0/bin/python.exe" finish_board.py kicad/tryN.ses
"""
import os, sys, json, math
import pcbnew
from pcbnew import FromMM, VECTOR2I

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
NAME = "safeboat-termica-v1"
BOARD_PATH = os.path.join(OUT_DIR, "kicad", NAME + ".kicad_pcb")
SES_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT_DIR, "kicad", "try1.ses")
OX, OY, HW, HH = 100.0, 100.0, 16.0, 16.0
ANT = (6.6, 10.55)     # keepout da antena: |x| <= 6.6 e y >= 10.55
SENSOR_C = (0.0, -9.5)


def P(x, y):
    return VECTOR2I(FromMM(OX + x), FromMM(OY - y))


def XY(v):
    return (pcbnew.ToMM(v.x) - OX, OY - pcbnew.ToMM(v.y))


board = pcbnew.LoadBoard(BOARD_PATH)
ok = pcbnew.ImportSpecctraSES(board, SES_PATH)
print("SES import:", ok, os.path.basename(SES_PATH))


class _Nets(dict):
    def __missing__(self, k):
        n = board.FindNet(k)
        if n is None:
            raise KeyError(k)
        return n


nets = _Nets()
FPS = {fp.GetReference(): fp for fp in board.GetFootprints()}

POWER = {"VIN_RAW", "VIN_F", "VIN", "3V3", "VDD_MLX", "VBUS"}


def _segd(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]; L2 = vx * vx + vy * vy
    if L2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0, min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy))


def _ssd(a, b, c, d):
    return min(_segd(a, c, d), _segd(b, c, d), _segd(c, a, b), _segd(d, a, b))


TR = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
VI = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
widened = 0
WIDE = 0.4
for t in TR:
    if t.GetNetname() not in POWER:
        continue
    a, b = XY(t.GetStart()), XY(t.GetEnd())
    okw = True
    for u in TR:
        if u is t or u.GetNetname() == t.GetNetname() or u.GetLayer() != t.GetLayer():
            continue
        need = WIDE / 2 + pcbnew.ToMM(u.GetWidth()) / 2 + 0.16
        if _ssd(a, b, XY(u.GetStart()), XY(u.GetEnd())) < need:
            okw = False; break
    if okw:
        for v in VI:
            if v.GetNetname() == t.GetNetname():
                continue
            need = WIDE / 2 + pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2 + 0.16
            if _segd(XY(v.GetPosition()), a, b) < need:
                okw = False; break
    if okw:
        for fp2 in board.GetFootprints():
            for pd in fp2.Pads():
                if pd.GetNetname() == t.GetNetname():
                    continue
                r = pd.GetBoundingBox()
                cx, cy = XY(pd.GetPosition())
                half = max(pcbnew.ToMM(r.GetWidth()), pcbnew.ToMM(r.GetHeight())) / 2
                if _segd((cx, cy), a, b) < half + WIDE / 2 + 0.16:
                    okw = False; break
            if not okw:
                break
    if okw:
        # borda: trilha larga não pode chegar a < 0,3 mm da borda
        if max(abs(a[0]), abs(b[0])) + WIDE / 2 > HW - 0.35 or max(abs(a[1]), abs(b[1])) + WIDE / 2 > HH - 0.35:
            okw = False
    if okw:
        t.SetWidth(FromMM(WIDE)); widened += 1
print("trilhas de potencia alargadas:", widened, "de", sum(1 for t in TR if t.GetNetname() in POWER))


def add_via(netname, x, y, size=0.6, drill=0.3):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y)); v.SetDrill(FromMM(drill)); v.SetWidth(FromMM(size))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(nets[netname]); board.Add(v)
    return v


# ---- serigrafia
def silk(text, x, y, size=0.8, layer=pcbnew.F_SilkS, mirror=False, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text); t.SetPosition(P(x, y))
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    t.SetTextThickness(FromMM(0.15 if size >= 0.8 else 0.12))
    t.SetLayer(layer); t.SetMirrored(mirror)
    if angle:
        t.SetTextAngleDegrees(angle)
    board.Add(t)


silk("+12V", -13.35, -7.0, 0.55); silk("GND", -9.85, -7.0, 0.55)
silk("USB 1:5V 2:D- 3:D+ 4:GND", 9.0, -6.9, 0.5)
silk("RST", 8.0, 13.8, 0.5, angle=90); silk("BOOT", 8.0, 9.7, 0.5, angle=90)
silk("TERMICA v1", -1.0, -6.0, 0.55)
# frente (lado do sensor): rótulos dos pinos + identificação
B = pcbnew.B_SilkS
silk("SDA", SENSOR_C[0] + 5.4, SENSOR_C[1] + 4.8, 0.5, B, True)
silk("VDD", SENSOR_C[0] + 5.4, SENSOR_C[1] - 4.8, 0.5, B, True)
silk("GND", SENSOR_C[0] - 5.4, SENSOR_C[1] - 4.8, 0.5, B, True)
silk("SCL", SENSOR_C[0] - 5.4, SENSOR_C[1] + 4.8, 0.5, B, True)
silk("SAFEBOAT TERMICA v1", 0, 5.0, 0.9, B, True)
silk("MLX90640 110: aba entre SCL e SDA", 0, 2.5, 0.6, B, True)
silk("frente: janela de germanio", 0, 0.5, 0.6, B, True)

# logo oficial vetorizada (arte única da família: safeboat-vibra/tools/logo-contours.json)
_logo_path = os.path.join(OUT_DIR, "..", "..", "..", "safeboat-vibra", "tools", "logo-contours.json")
if os.path.exists(_logo_path):
    _LOGO = json.load(open(_logo_path))

    def add_logo_silk(od, cx, cy, layer=pcbnew.F_SilkS, mirror=False):
        sc = od / _LOGO["od"]
        byd = {}
        for loop in _LOGO["loops"]:
            byd.setdefault(loop["depth"], []).append(loop["pts"])
        result = pcbnew.SHAPE_POLY_SET()
        for d in sorted(byd):
            stage = pcbnew.SHAPE_POLY_SET()
            for pts in byd[d]:
                sgn = -1 if mirror else 1
                tp = [(cx - sgn * px * sc, cy + py * sc) for px, py in pts]
                area = 0.0
                for i in range(len(tp)):
                    x1, y1 = tp[i]; x2, y2 = tp[(i + 1) % len(tp)]
                    area += x1 * y2 - x2 * y1
                if area < 0:
                    tp.reverse()
                chain = pcbnew.SHAPE_LINE_CHAIN()
                for qx, qy in tp:
                    chain.Append(P(qx, qy))
                chain.SetClosed(True)
                stage.AddOutline(chain)
            try:
                if d % 2 == 0: result.BooleanAdd(stage)
                else:          result.BooleanSubtract(stage)
            except TypeError:
                if d % 2 == 0: result.BooleanAdd(stage, pcbnew.SHAPE_POLY_SET.PM_FAST)
                else:          result.BooleanSubtract(stage, pcbnew.SHAPE_POLY_SET.PM_FAST)
        try:
            result.Fracture()
        except TypeError:
            result.Fracture(pcbnew.SHAPE_POLY_SET.PM_FAST)
        for oi in range(result.OutlineCount()):
            single = pcbnew.SHAPE_POLY_SET()
            single.AddOutline(result.COutline(oi))
            sh = pcbnew.PCB_SHAPE(board)
            sh.SetShape(pcbnew.SHAPE_T_POLY)
            sh.SetPolyShape(single); sh.SetFilled(True); sh.SetWidth(0)
            sh.SetLayer(layer); board.Add(sh)

    add_logo_silk(5.5, 0.0, 11.0, pcbnew.B_SilkS, True)
else:
    print("logo-contours.json nao encontrado — sem logo")

filler = pcbnew.ZONE_FILLER(board)


def clear_at(x, y, keep=0.45):
    for tt in board.GetTracks():
        if tt.GetNetname() == "GND":
            continue
        if tt.GetClass() == "PCB_VIA":
            xx, yy = XY(tt.GetPosition())
            if math.hypot(x - xx, y - yy) < keep + 0.35:
                return False
        else:
            aa, bb = XY(tt.GetStart()), XY(tt.GetEnd())
            if _segd((x, y), aa, bb) < keep + 0.2:
                return False
    for fp2 in board.GetFootprints():
        for pd in fp2.Pads():
            xx, yy = XY(pd.GetPosition())
            if pd.GetNetname() == "GND" and pd.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                continue
            if math.hypot(x - xx, y - yy) < keep + 0.9:
                return False
    inside = abs(x) <= HW - 1.2 and abs(y) <= HH - 1.2
    antena = (abs(x) <= ANT[0] + 0.4 and y >= ANT[1] - 0.4)
    sensor = math.hypot(x - SENSOR_C[0], y - SENSOR_C[1]) < 3.8
    return inside and not antena and not sensor


def gnd_pts_all():
    pts = [tt.GetPosition() for tt in board.GetTracks() if tt.GetClass() == "PCB_VIA" and tt.GetNetname() == "GND"]
    for fp2 in board.GetFootprints():
        for pd in fp2.Pads():
            if pd.GetNetname() == "GND" and pd.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                pts.append(pd.GetPosition())
    return pts


def stitch(rounds=2):
    total = 0
    for _ in range(rounds):
        filler.Fill(board.Zones())
        fz = None
        for zz in board.Zones():
            if not zz.GetIsRuleArea() and zz.GetNetname() == "GND" and zz.GetLayer() == pcbnew.F_Cu:
                fz = zz
        if fz is None:
            return total
        polys = fz.GetFilledPolysList(pcbnew.F_Cu)
        gnd_pts = gnd_pts_all()
        added = 0
        for i in range(polys.OutlineCount()):
            ol = polys.COutline(i)
            if any(ol.PointInside(p) for p in gnd_pts):
                continue
            bb = ol.BBox()
            cx = (pcbnew.ToMM(bb.GetLeft()) + pcbnew.ToMM(bb.GetRight())) / 2 - OX
            cy = OY - (pcbnew.ToMM(bb.GetTop()) + pcbnew.ToMM(bb.GetBottom())) / 2
            cands = [(cx, cy)]
            n = ol.PointCount()
            for k in range(0, n, max(1, n // 24)):
                vx, vy = XY(ol.CPoint(k))
                for f in (0.35, 0.6):
                    cands.append((vx + (cx - vx) * f, vy + (cy - vy) * f))
            for (qx, qy) in cands:
                if ol.PointInside(P(qx, qy)) and clear_at(qx, qy):
                    add_via("GND", qx, qy, size=0.5, drill=0.3); added += 1
                    break
        total += added
        if not added:
            break
    return total


print("vias de costura:", stitch())


def gnd_bridge(max_iter=20):
    for _ in range(max_iter):
        filler.Fill(board.Zones())
        F, Bz = [], []
        for zz in board.Zones():
            if zz.GetIsRuleArea() or zz.GetNetname() != "GND":
                continue
            polys = zz.GetFilledPolysList(zz.GetLayer())
            dst = F if zz.GetLayer() == pcbnew.F_Cu else Bz
            for i in range(polys.OutlineCount()):
                dst.append(polys.COutline(i))
        pts = gnd_pts_all()
        n = len(F) + len(Bz)
        parent = list(range(n))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]; a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for p in pts:
            hit = [i for i, ol in enumerate(F) if ol.PointInside(p)] + [len(F) + j for j, ol in enumerate(Bz) if ol.PointInside(p)]
            for k in hit[1:]:
                union(hit[0], k)
        comps = {}
        for k in range(n):
            comps.setdefault(find(k), []).append(k)
        print("GND: ilhas F=%d B=%d aglomerados=%d" % (len(F), len(Bz), len(comps)))
        if len(comps) <= 1:
            return True
        placed = False
        grid = [(-HW + 1.0 + 0.5 * i) for i in range(int((2 * HW - 2) / 0.5) + 1)]
        for y in grid:
            for x in grid:
                q = P(x, y)
                fi = next((i for i, ol in enumerate(F) if ol.PointInside(q)), None)
                bj = next((j for j, ol in enumerate(Bz) if ol.PointInside(q)), None)
                if fi is None or bj is None:
                    continue
                if find(fi) == find(len(F) + bj):
                    continue
                if not clear_at(x, y):
                    continue
                add_via("GND", x, y, size=0.5, drill=0.3)
                print("via de ponte GND em (%.1f, %.1f)" % (x, y)); placed = True
                break
            if placed:
                break
        if not placed:
            print("AVISO: nenhum ponto livre para unir os aglomerados de GND"); return False
    return False


gnd_bridge()
filler.Fill(board.Zones())
pcbnew.SaveBoard(BOARD_PATH, board)
print("fase 2 ok — itens de trilha:", len(list(board.GetTracks())))

pro = {
    "board": {"design_settings": {"rules": {
        "min_clearance": 0.0, "min_connection": 0.0, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.25,
        "min_hole_to_hole": 0.25, "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1, "min_silk_clearance": 0.0,
        "min_text_height": 0.5, "min_text_thickness": 0.08, "min_through_hole_diameter": 0.3, "min_track_width": 0.15,
        "min_via_annular_width": 0.1, "min_via_diameter": 0.5},
        "rule_severities": {"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore",
                            "silk_overlap": "warning", "silk_over_copper": "warning", "footprint_type_mismatch": "ignore"}}},
    "net_settings": {"classes": [{
        "name": "Default", "bus_width": 12, "clearance": 0.148, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3, "wire_width": 6}], "meta": {"version": 4}},
    "erc": {"erc_exclusions": [], "meta": {"version": 0},
            "rule_severities": {"footprint_link_issues": "ignore", "lib_symbol_issues": "ignore",
                                "lib_symbol_mismatch": "ignore", "endpoint_off_grid": "warning"}},
    "meta": {"filename": NAME + ".kicad_pro", "version": 3}
}
open(os.path.join(OUT_DIR, "kicad", NAME + ".kicad_pro"), "w").write(json.dumps(pro, indent=2))
print("kicad_pro gravado")
