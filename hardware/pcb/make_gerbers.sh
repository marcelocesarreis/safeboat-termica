#!/bin/bash
# SAFEBOAT TERMICA v1 — pacote de fabricacao JLCPCB (gerbers + drill + zip)
set -e
cd "$(dirname "$0")"
KCLI="$LOCALAPPDATA/Programs/KiCad/10.0/bin/kicad-cli.exe"
NAME=safeboat-termica-v1
BOARD=kicad/$NAME.kicad_pcb
OUT=jlcpcb/gerbers
rm -rf "$OUT" && mkdir -p "$OUT"

"$KCLI" pcb export gerbers \
  --layers "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts" \
  --subtract-soldermask --use-drill-file-origin \
  --output "$OUT/" "$BOARD"

"$KCLI" pcb export drill \
  --format excellon --drill-origin absolute --excellon-units mm \
  --excellon-zeros-format decimal --generate-map --map-format gerberx2 \
  --output "$OUT/" "$BOARD"

cd jlcpcb
rm -f $NAME-gerbers.zip
powershell.exe -NoProfile -Command "Compress-Archive -Path 'gerbers\\*' -DestinationPath '$NAME-gerbers.zip' -Force"
echo "== pacote =="
ls -la $NAME-gerbers.zip | awk '{print $5, $9}'
