#!/bin/bash
# HRMA Windows payload kurucu (Mac üstünde cross-hazırlık)
set -euo pipefail

B="$(cd "$(dirname "$0")" && pwd)"
SRC="/Users/apple/Desktop/dosyalar/HRMA"
W="$B/win/payload"

echo "[1/5] Gömülü Python..."
rm -rf "$W"
mkdir -p "$W/python" "$W/libs" "$W/app"
unzip -q "$B/runtime/python-embed-win.zip" -d "$W/python"

# ._pth: gömülü python'un yol haritası (exe dizinine göre görelidir)
cat > "$W/python/python312._pth" <<'PTH'
python312.zip
.
..\libs
..\app
import site
PTH

# .pth dosyalarının işlenmesi için libs'i gerçek site dizini olarak kaydet
cat > "$W/python/sitecustomize.py" <<'SC'
import os
import site

_here = os.path.dirname(os.path.abspath(__file__))
for _d in ("libs", "app"):
    _p = os.path.abspath(os.path.join(_here, os.pardir, _d))
    if os.path.isdir(_p):
        site.addsitedir(_p)
SC

echo "[2/5] win_amd64 wheel kurulumu (1. aşama)..."
python3 -m pip install --target "$W/libs" \
    --platform win_amd64 --python-version 3.12 --implementation cp \
    --only-binary=:all: -r "$B/requirements_bundle.txt" \
    --no-warn-script-location

echo "[3/5] 2. aşama (--no-deps: build123d, ocp-gordon, rocketcea)..."
python3 -m pip install --target "$W/libs" \
    --platform win_amd64 --python-version 3.12 --implementation cp \
    --only-binary=:all: --no-deps \
    build123d==0.11.1 ocp-gordon==0.2.0 rocketcea==1.2.1 \
    --no-warn-script-location

echo "[4/5] Uygulama kaynakları..."
rsync -a --exclude='__pycache__' "$SRC/hrma" "$W/app/"
rsync -a "$SRC/data" "$W/app/"
cp "$B/launcher.py" "$W/app/launcher.py"

echo "[5/5] Temizlik + boyut:"
find "$W/libs" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W/libs/bin" 2>/dev/null || true
du -sh "$W"
echo "TAMAM: $W"
