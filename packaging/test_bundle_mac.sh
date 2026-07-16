#!/bin/bash
# Mac bundle doğrulama: import + sunucu + kritik uçlar
set -uo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
RES="$B/mac/build.noindex/HRMA.app/Contents/Resources"
PY="$RES/python/bin/python3.12"
export RES

if curl -s -o /dev/null --max-time 2 http://127.0.0.1:8085/; then
  echo "HATA: 8085 portunda zaten bir sunucu var, test sağlıklı olmaz. Önce onu kapat."
  exit 1
fi

echo "== 1) Python sürümü =="
"$PY" --version || exit 1

echo "== 2) Import duman testi (bundle yollarıyla) =="
"$PY" - <<'EOF' || exit 1
import os, sys, site
res = os.environ["RES"]
site.addsitedir(os.path.join(res, "libs"))
sys.path.insert(0, os.path.join(res, "libs"))
sys.path.insert(0, os.path.join(res, "app"))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy, scipy, plotly, pandas, matplotlib, flask, waitress, trimesh
print("temel paketler OK:", numpy.__version__, scipy.__version__, plotly.__version__)

import build123d
print("build123d OK:", build123d.__version__)

from hrma.export.step_export import BUILD123D_AVAILABLE
print("BUILD123D_AVAILABLE:", BUILD123D_AVAILABLE)
assert BUILD123D_AVAILABLE, "STEP export devre dışı kalırdı!"

from hrma.analysis.tank_blowdown import COOLPROP_AVAILABLE
print("COOLPROP_AVAILABLE:", COOLPROP_AVAILABLE)
assert COOLPROP_AVAILABLE

try:
    from rocketcea.cea_obj import CEA_Obj
    print("rocketcea OK")
except Exception as e:
    print("rocketcea YOK (fallback devrede):", e)

from hrma.app import app
print("hrma.app OK, route sayısı:", len(list(app.url_map.iter_rules())))
EOF

echo "== 3) Sunucu ucu testi (launcher üzerinden) =="
export RES
LOG="$B/mac_server_test.log"
HRMA_PORT=8085 "$PY" "$RES/app/launcher.py" > "$LOG" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

for i in $(seq 1 60); do
  if curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8085/ | grep -q 200; then break; fi
  sleep 1
done
CODE=$(curl -s -o /tmp/hrma_index.html -w '%{http_code}' http://127.0.0.1:8085/)
echo "GET / -> $CODE"
grep -q "HRMA" /tmp/hrma_index.html && echo "index içerik OK" || { echo "INDEX HATALI"; cat "$LOG"; exit 1; }
kill $SRV 2>/dev/null
trap - EXIT
echo "== BUNDLE TESTLERI BASARILI =="
