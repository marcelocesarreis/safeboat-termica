# -*- coding: utf-8 -*-
"""Pós-DRC: trilhas alargadas (0,4 mm) que caíram em violação de isolamento voltam a 0,25 mm.
Roda depois do DRC (kicad/drc.json); o pipeline repete DRC até zerar (máx. 3 voltas)."""
import os, json, math
import pcbnew
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(OUT_DIR, "kicad", "safeboat-termica-v1.kicad_pcb")
d = json.load(open(os.path.join(OUT_DIR, "kicad", "drc.json"), encoding="utf-8"))
pts = []
for v in d.get("violations", []):
    if v["severity"] != "error" or v["type"] not in ("clearance", "copper_edge_clearance", "hole_clearance"):
        continue
    for it in v.get("items", []):
        if it["description"].startswith("Trilha") or it["description"].startswith("Track"):
            pts.append((it["pos"]["x"], it["pos"]["y"]))
# alívio térmico faminto: o pad passa a conexão sólida com o plano (reflow da JLC não se importa)
starved = [(it["pos"]["x"], it["pos"]["y"]) for v in d.get("violations", []) if v["type"] == "starved_thermal" for it in v.get("items", []) if "Ilha" in it["description"] or "Pad" in it["description"]]
dang = []   # tocos pendurados: só aviso (remover quebrava a conexão quando a ponta caía num plano)
if not pts and not dang and not starved:
    print("fix_drc: nada a corrigir"); raise SystemExit(0)
b = pcbnew.LoadBoard(BOARD)
n = 0
ns = 0
for fp in b.GetFootprints():
    for pd in fp.Pads():
        px, py = pcbnew.ToMM(pd.GetPosition().x), pcbnew.ToMM(pd.GetPosition().y)
        if any(math.hypot(px - sx, py - sy) < 0.05 for sx, sy in starved):
            pd.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL); ns += 1
# lição do VIB: SWIG quebra os iteradores depois de Remove() — capturar a lista UMA vez antes
TRK = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
removed = set()
# trilhas penduradas (sobra do roteador): remove o segmento cuja ponta é o item reportado
for t in TRK:
    for (px, py) in dang:
        hit = any(math.hypot(pcbnew.ToMM(q.x) - px, pcbnew.ToMM(q.y) - py) < 0.01 for q in (t.GetStart(), t.GetEnd()))
        if hit:
            removed.add(id(t)); break
for t in TRK:
    if id(t) in removed:
        continue
    if pcbnew.ToMM(t.GetWidth()) < 0.3:
        continue
    a = (pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)); e = (pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y))
    for (px, py) in pts:
        # ponto reportado está sobre o segmento (distância ao segmento < 0,25)
        vx, vy = e[0] - a[0], e[1] - a[1]; L2 = vx * vx + vy * vy or 1e-9
        tt = max(0, min(1, ((px - a[0]) * vx + (py - a[1]) * vy) / L2))
        if math.hypot(px - (a[0] + tt * vx), py - (a[1] + tt * vy)) < 0.25:
            t.SetWidth(pcbnew.FromMM(0.25)); n += 1; break
for t in TRK:
    if id(t) in removed:
        b.Remove(t)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(BOARD, b)
print("fix_drc: trilhas estreitadas:", n, "| penduradas removidas:", len(removed), "| pads solidos:", ns)
