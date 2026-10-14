# -*- coding: utf-8 -*-
"""Anexa os modelos 3D próprios (lib/3d/*.wrl) aos footprints U3 (MLX90640) e J2 (KF350) da placa pronta,
sem tocar no roteamento. make_board.py já faz o mesmo ao regenerar a placa."""
import os
import pcbnew
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(OUT_DIR, "kicad", "safeboat-termica-v1.kicad_pcb")
MODELS = {"U3": "${KIPRJMOD}/../lib/3d/MLX90640_TO-39-110.wrl", "J2": "${KIPRJMOD}/../lib/3d/KF350-3.5-2P.wrl"}
b = pcbnew.LoadBoard(BOARD)
n = 0
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref not in MODELS:
        continue
    fp.Models().clear()
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = MODELS[ref]
    m.m_Show = True
    fp.Models().push_back(m)
    n += 1
pcbnew.SaveBoard(BOARD, b)
print("modelos anexados:", n)
