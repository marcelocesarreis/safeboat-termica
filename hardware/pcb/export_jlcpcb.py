# -*- coding: utf-8 -*-
"""
SAFEBOAT TERMICA v1 — fase 3: BOM + CPL para montagem JLCPCB (gerbers pelo make_gerbers.sh).
Gera jlcpcb/BOM-safeboat-termica-v1.csv e jlcpcb/CPL-safeboat-termica-v1.csv (dois lados: U3 no Bottom).
Códigos LCSC verificados em 22/09/2026 (busca web) salvo os marcados VERIFICAR — regra da casa:
conferir código/encapsulamento/estoque no carrinho antes de pagar (editar peça DESMARCA a linha;
remarcar o checkbox).
"""
import os, csv
import pcbnew

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
NAME = "safeboat-termica-v1"
BOARD_PATH = os.path.join(OUT_DIR, "kicad", NAME + ".kicad_pcb")
PROD = os.path.join(OUT_DIR, "jlcpcb")
os.makedirs(PROD, exist_ok=True)
board = pcbnew.LoadBoard(BOARD_PATH)
OX, OY = 100.0, 100.0

LCSC = {
    "U1": ("ESP32-C3-MINI-1-N4", "C2934569"),
    "U2": ("AP63203WU-7 buck 3.3V 2A 32V", "C780769"),
    "U3": ("MLX90640ESF-BAA-000-TU (TO-39, 110x75 graus) - THT no lado B (frente)", "C17380659"),
    "J2": ("KF350-3.5-2P borne 3.5mm 2p", "C474892"),
    "Q1": ("SI2301CDS PMOS SOT-23", "C10487"),
    "D1": ("SMAJ26A-TR TVS 26V SMA", "C132945"),
    "D2": ("SS34 Schottky 3A 40V SMA", "VERIFICAR (ex. C8678)"),
    "D3": ("SS14 Schottky 1A 40V SMA", "VERIFICAR (ex. C2480)"),
    "L1": ("SWPA4020S4R7MT 4.7uH 1.34A", "C48427"),
    "F1": ("SMD1812P050TF/60 PPTC 0.5A 60V", "C462518"),
    "J1": ("JST B4B-PH-K-S 4p 2.0mm", "C131334"),
    "SW1": ("KMR221GLFS", "C72443"), "SW2": ("KMR221GLFS", "C72443"),
    "LED1": ("LTST-C190KFKT ambar", "C157740"),
    "C2": ("100nF 50V X7R 0603", "C14663"), "C4": ("100nF 50V X7R 0603", "C14663"),
    "C8": ("100nF 50V X7R 0603", "C14663"), "C10": ("100nF 50V X7R 0603", "C14663"),
    "C1": ("1uF 0603", "C15849"),
    "C3": ("10uF 0603 X5R", "C19702"),
    "C9": ("10uF 10V X5R 0805", "basico JLC por valor"),
    "C6": ("22uF 10V X5R 0805", "VERIFICAR"), "C7": ("22uF 10V X5R 0805", "VERIFICAR"),
    "C5": ("10uF 50V X7R 1210", "VERIFICAR"),
    "R1": ("10k 0603", "C25804"), "R4": ("1k 0603", "C21190"), "R6": ("1k 0603", "C21190"),
    "R2": ("2.2k 0603", "basico JLC por valor"), "R3": ("2.2k 0603", "basico JLC por valor"),
    "R5": ("100k 0603", "C25803"), "R7": ("200k 0603", "basico JLC por valor"), "R8": ("20k 0603", "basico JLC por valor"),
}
dnp = set(open(os.path.join(OUT_DIR, "kicad", "dnp.txt")).read().split())

rows = {}
cpl = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if fp.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM:
        continue
    val = fp.GetValue()
    fpid = str(fp.GetFPID().GetLibItemName())
    part, lcsc = LCSC.get(ref, (val, "basico JLC por valor"))
    rows[ref] = (part, fpid, lcsc)
    if ref not in dnp:
        pos = fp.GetPosition()
        cpl.append([ref, round(pcbnew.ToMM(pos.x) - OX, 3), round(-(pcbnew.ToMM(pos.y) - OY), 3),
                    "Bottom" if fp.IsFlipped() else "Top", round(fp.GetOrientationDegrees(), 1)])


def write_bom(fname, refs):
    grp = {}
    for r in refs:
        part, fpid, lcsc = rows[r]
        grp.setdefault((part, fpid, lcsc), []).append(r)
    with open(os.path.join(PROD, fname), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (part, fpid, lcsc), rr in sorted(grp.items(), key=lambda kv: kv[1][0]):
            w.writerow([part, ",".join(sorted(rr)), fpid, lcsc])


pcba_refs = [r for r in rows if r not in dnp]
write_bom("BOM-%s.csv" % NAME, pcba_refs)
write_bom("BOM-%s-COMPLETA.csv" % NAME, list(rows))
with open(os.path.join(PROD, "CPL-%s.csv" % NAME), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for row in sorted(cpl):
        w.writerow(row)
print("PCBA:", len(pcba_refs), "componentes montados pela JLC;", "fora da PCBA:", sorted(dnp))
