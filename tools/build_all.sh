#!/usr/bin/env bash
# Rebuild every release variant from the stock image and make BPS patches.
#   tools/build_all.sh [STOCK.bin]
# Outputs: firmware/build/*.json (patch sets, tracked)
#          firmware/work/<variant>/2D15P_V2.7.0.7_260826.bin (images, untracked)
#          firmware/work/release/*.bps (for GitHub releases, untracked)
set -euo pipefail
cd "$(dirname "$0")/.."
STOCK=${1:-firmware/stock/2D15P_V2.7.0.7_260826.bin}
NAME=2D15P_V2.7.0.7_260826.bin
mkdir -p firmware/work/release firmware/work/dmm-first

python3 tools/fw_patch.py "$STOCK" firmware/dmm-first.json -o firmware/work/dmm-first/$NAME | tail -1
for ADDON in dmm-stream dmm-rel; do
  python3 tools/fw_patch.py firmware/work/dmm-first/$NAME <(python3 -c "import json;j=json.load(open('firmware/$ADDON.json'));j.pop('input_crc32');j.pop('require_size');print(json.dumps(j))") -o firmware/work/dmm-first/$NAME
done
python3 tools/bps_make.py "$STOCK" firmware/work/dmm-first/$NAME firmware/work/release/2D15P_V2.7.0.7_dmm-first.bps

for f in lang/*.json; do
    code=$(basename "$f" .json)
    case $code in slots|layout) continue ;; esac
    python3 tools/lang_build.py "$STOCK" "$code" --image | grep -Ev '^WIDE'
    python3 tools/bps_make.py "$STOCK" firmware/work/dmm-first+$code/$NAME \
        firmware/work/release/2D15P_V2.7.0.7_dmm-first+$code.bps
done
(cd firmware/work/release && sha256sum *.bps > SHA256SUMS && cat SHA256SUMS)
