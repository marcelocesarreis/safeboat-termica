# -*- coding: utf-8 -*-
"""Courtyards REAIS: sobreposição, saída da placa 40 x 40 (margem 0,3), recortes da antena, faixa da antena
(nada metálico ao lado: só o módulo acima de y = 13,35 e nada com |x| <= 9,9 lá), furos (raio livre 2,3) e
zona dos pinos do sensor."""
import os, itertools, math
import pcbnew
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(OUT_DIR, "kicad", "safeboat-termica-v1.kicad_pcb")
OX, OY, HW, HH = 100.0, 100.0, 20.0, 20.0
NOTCH_X0, NOTCH_X1, NOTCH_Y = 6.9, 10.2, 14.35
b = pcbnew.LoadBoard(BOARD)
boxes = {}
holes = []
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith("H"):
        p = fp.GetPosition(); holes.append((pcbnew.ToMM(p.x) - OX, OY - pcbnew.ToMM(p.y)))
        continue
    layer = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
    c = fp.GetCourtyard(layer)
    bb = c.BBox() if c.OutlineCount() else None
    if bb is None:
        for pd in fp.Pads():
            r = pd.GetBoundingBox()
            if bb is None:
                bb = pcbnew.BOX2I(r.GetPosition(), r.GetSize())
            else:
                bb.Merge(r)
    boxes[ref] = (pcbnew.ToMM(bb.GetLeft()) - OX, OY - pcbnew.ToMM(bb.GetBottom()), pcbnew.ToMM(bb.GetRight()) - OX, OY - pcbnew.ToMM(bb.GetTop()), fp.IsFlipped())
SENSOR_PADS = []
for fp in b.GetFootprints():
    if fp.GetReference() == "U3":
        for pd in fp.Pads():
            r = pd.GetBoundingBox()
            SENSOR_PADS.append((pcbnew.ToMM(r.GetLeft()) - OX, OY - pcbnew.ToMM(r.GetBottom()), pcbnew.ToMM(r.GetRight()) - OX, OY - pcbnew.ToMM(r.GetTop())))
bad = 0
for (a, A), (c, C) in itertools.combinations(boxes.items(), 2):
    if A[4] != C[4]:
        continue
    ox = min(A[2], C[2]) - max(A[0], C[0]); oy = min(A[3], C[3]) - max(A[1], C[1])
    if ox > 0.01 and oy > 0.01:
        print("OVERLAP %s x %s  (%.2f x %.2f mm)" % (a, c, ox, oy)); bad += 1


def box_dist(bx, pt):
    dx = max(bx[0] - pt[0], 0, pt[0] - bx[2]); dy = max(bx[1] - pt[1], 0, pt[1] - bx[3])
    return math.hypot(dx, dy)


for r_, (x0, y0, x1, y1, fl) in boxes.items():
    m = 0.0 if r_ == "U1" else 0.3
    if x0 < -HW + m - 0.06 or x1 > HW - m + 0.06 or y0 < -HH + m - 0.06 or y1 > HH - m + 0.06:
        print("FORA DA PLACA %s  bbox=%.2f,%.2f..%.2f,%.2f" % (r_, x0, y0, x1, y1)); bad += 1
    if r_ != "U1":
        # recortes da antena e faixa da antena
        if y1 > NOTCH_Y - 0.3 and x1 > -NOTCH_X1 - 0.3 and x0 < NOTCH_X1 + 0.3:
            print("NO RECORTE/FAIXA DA ANTENA %s" % r_); bad += 1
        elif y1 > NOTCH_Y:
            print("aviso: %s nas orelhas acima da antena (y1=%.1f)" % (r_, y1))
        for hx, hy in holes:
            if box_dist((x0, y0, x1, y1), (hx, hy)) < 2.3 - 0.01:
                print("SOB A CABECA DO PARAFUSO (%.1f,%.1f): %s" % (hx, hy, r_)); bad += 1
    if r_ != "U3" and not fl:
        for (sx0, sy0, sx1, sy1) in SENSOR_PADS:
            if x0 < sx1 + 0.2 and x1 > sx0 - 0.2 and y0 < sy1 + 0.2 and y1 > sy0 - 0.2:
                print("SOBRE OS PINOS DO SENSOR %s" % r_); bad += 1; break
mins = []
for (a, A), (c, C) in itertools.combinations(boxes.items(), 2):
    if A[4] != C[4]:
        continue
    gx = max(A[0], C[0]) - min(A[2], C[2]); gy = max(A[1], C[1]) - min(A[3], C[3])
    g = max(gx, gy)
    if g < 0.3:
        mins.append((round(g, 2), a, c))
print("gaps < 0,3 mm:", sorted(mins)[:14])
print("problemas:", bad)
