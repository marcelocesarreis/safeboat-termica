# compara redes pino a pino: PCB (pads) x esquematico (sch_nets.json)
import os, json, pcbnew
OUT = os.path.dirname(os.path.abspath(__file__))
b = pcbnew.LoadBoard(os.path.join(OUT, 'kicad', 'safeboat-termica-v1.kicad_pcb'))
sch = json.load(open(os.path.join(OUT, 'kicad', 'sch_nets.json')))
pcb = {}
for fp in b.GetFootprints():
    for pd in fp.Pads():
        if pd.GetNetname():
            pcb.setdefault(fp.GetReference(), {})[pd.GetName()] = pd.GetNetname()
dif = 0
for ref in sorted(set(sch) | set(pcb)):
    if ref.startswith('#'):
        continue
    a = sch.get(ref, {}); p = pcb.get(ref, {})
    for pin in sorted(set(a) | set(p), key=str):
        if a.get(pin) != p.get(pin):
            print('DIF', ref, pin, 'sch=', a.get(pin), 'pcb=', p.get(pin)); dif += 1
print('diferencas:', dif)
