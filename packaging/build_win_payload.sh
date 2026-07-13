#!/bin/bash
# HRMA Windows payload kurucu (Mac üstünde cross-hazırlık)
set -euo pipefail

B="$(cd "$(dirname "$0")" && pwd)"
SRC="/Users/apple/Desktop/dosyalar/HRMA"
W="$B/win/payload"

echo "[1/6] Gömülü Python..."
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

echo "[2/6] win_amd64 wheel kurulumu (1. aşama)..."
python3 -m pip install --target "$W/libs" \
    --platform win_amd64 --python-version 3.12 --implementation cp \
    --only-binary=:all: -r "$B/requirements_bundle.txt" \
    --no-warn-script-location

echo "[3/6] 2. aşama (--no-deps: build123d, ocp-gordon, rocketcea, pywebview)..."
# pywebview zinciri de --no-deps + açık liste: pip, environment marker'ları
# ÇALIŞAN yorumlayıcıya (macOS) göre değerlendirir; markers'a bırakılırsa
# Windows bundle'ına pythonnet yerine pyobjc girer (2026-07-14 tespiti).
# pythonnet>=3.1 şart: 3.0.x Requires-Python <3.12 deklare ediyor.
python3 -m pip install --target "$W/libs" \
    --platform win_amd64 --python-version 3.12 --implementation cp \
    --only-binary=:all: --no-deps \
    build123d==0.11.1 ocp-gordon==0.2.0 rocketcea==1.2.1 \
    pywebview==6.2.1 pythonnet==3.1.0 clr_loader==0.3.1 \
    cffi==1.17.1 pycparser==2.22 bottle==0.13.4 \
    --no-warn-script-location

# proxy_tools: PyPI'da yalnız sdist var (wheel yok) → --only-binary ile inmez.
# Saf Python olduğu için yerelde derlenen wheel Windows'ta birebir çalışır.
python3 -m pip install --target "$W/libs" --no-deps proxy_tools==0.1.0 \
    --no-warn-script-location

echo "[4/6] Uygulama kaynakları..."
rsync -a --exclude='__pycache__' "$SRC/hrma" "$W/app/"
rsync -a "$SRC/data" "$W/app/"
cp "$B/launcher.py" "$W/app/launcher.py"

echo "[5/6] Bytecode ön-derleme (ilk açılışı hızlandırır)..."
# .pyc formatı platformdan bağımsızdır; sürüm eşleşmesi yeter (3.12 ↔ 3.12).
# __pycache__ artık SİLİNMİYOR — ilk açılışta derleme bedeli kalkıyor.
python3 - <<'VERCHECK'
import sys
assert sys.version_info[:2] == (3, 12), (
    "compileall python'u 3.12 olmalı (gömülü python312 ile eşleşme), "
    "bulunan: %s" % sys.version)
VERCHECK
python3 -m compileall -q -j 0 "$W/libs" "$W/app" || true

echo "[6/6] Temizlik + boyut:"
rm -rf "$W/libs/bin" 2>/dev/null || true
du -sh "$W"
echo "TAMAM: $W"
