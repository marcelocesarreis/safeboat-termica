#!/bin/bash
# SAFEBOAT TERMICA v1 — fase 2 em diante: SES -> acabamento -> DRC -> renders -> BOM/CPL -> gerbers
# uso: bash pipeline_final.sh kicad/tryN.ses
set -e
cd "$(dirname "$0")"
SES=${1:-kicad/try1.ses}
PY="$LOCALAPPDATA/Programs/KiCad/10.0/bin/python.exe"
KCLI="$LOCALAPPDATA/Programs/KiCad/10.0/bin/kicad-cli.exe"
B=kicad/safeboat-termica-v1.kicad_pcb
echo "== finish_board ($SES)"; "$PY" finish_board.py "$SES" 2>&1 | grep -v "^$" | tail -8
for k in 1 2 3; do
  echo "== DRC (volta $k)"; "$KCLI" pcb drc --format json --severity-all --all-track-errors --output kicad/drc.json "$B" 2>&1 | tail -1
  "$PY" fix_drc.py | tail -1 | grep -q "nada a corrigir" && break
done
PYTHONIOENCODING=utf-8 python - <<'EOF'
import json
from collections import Counter
d=json.load(open('kicad/drc.json',encoding='utf-8'))
v=d.get('violations',[]); u=d.get('unconnected_items',[])
err=[x for x in v if x['severity']=='error']
print('DRC: erros',len(err),'avisos',len(v)-len(err),'desconectados',len(u), Counter(x['type'] for x in err))
for x in u[:12]: print(' U', ' ; '.join(i['description'][:48] for i in x.get('items',[])))
for x in err[:12]: print(' E',x['type'],x['description'][:80],[(round(i['pos']['x']-100,2),round(100-i['pos']['y'],2)) for i in x.get('items',[])][:1])
EOF
echo "== renders"
"$KCLI" pcb render --side top --zoom 1.0 --width 1400 --height 1400 --background opaque --quality high --output kicad/render-top.png "$B" 2>&1 | tail -1
"$KCLI" pcb render --side bottom --zoom 1.0 --width 1400 --height 1400 --background opaque --quality high --output kicad/render-bottom.png "$B" 2>&1 | tail -1
"$KCLI" pcb render --side top --rotate "-30,0,30" --zoom 0.9 --width 1400 --height 1400 --background opaque --quality high --output kicad/render-iso.png "$B" 2>&1 | tail -1
"$KCLI" pcb export svg --layers "F.Cu,F.SilkS,F.Mask,Edge.Cuts" --page-size-mode 2 --exclude-drawing-sheet --output kicad/layout-top.svg "$B" 2>&1 | tail -1
"$KCLI" pcb export svg --layers "B.Cu,B.SilkS,B.Mask,Edge.Cuts" --page-size-mode 2 --exclude-drawing-sheet --mirror --output kicad/layout-bottom.svg "$B" 2>&1 | tail -1
echo "== BOM/CPL"; "$PY" export_jlcpcb.py 2>&1 | grep -v "^$" | tail -2
echo "== gerbers"; bash make_gerbers.sh 2>&1 | tail -2
