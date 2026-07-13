#!/bin/bash
# HRMA.app + DMG kurucu (macOS arm64)
set -euo pipefail

B="$(cd "$(dirname "$0")" && pwd)"
SRC="/Users/apple/Desktop/dosyalar/HRMA"
APP="$B/mac/HRMA.app"
RES="$APP/Contents/Resources"

# Sürüm tek kaynaktan: hrma/__init__.py
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/hrma/__init__.py")"
[ -n "$VERSION" ] || { echo "HATA: sürüm okunamadı"; exit 1; }
echo "Sürüm: $VERSION"

echo "[1/7] İskelet..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>HRMA</string>
    <key>CFBundleDisplayName</key><string>HRMA</string>
    <key>CFBundleIdentifier</key><string>com.uzaytek.hrma</string>
    <key>CFBundleVersion</key><string>${VERSION}</string>
    <key>CFBundleShortVersionString</key><string>${VERSION}</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>HRMA</string>
    <key>CFBundleIconFile</key><string>icon.icns</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <!-- LSUIElement KALDIRILDI (2026-07-14): pencere artık pywebview ile
         süreç içinde açılıyor; uygulama Dock'ta normal görünür. Eski
         "sonsuz zıplama" sorunu sunucunun arka plana atılıp stub'ın hemen
         çıkmasından kaynaklanıyordu; şimdi python ön planda çalışıyor. -->
</dict>
</plist>
PLIST

# Ana çalıştırılabilir GERÇEK arm64 binary olmalı: script olursa macOS
# mimariyi belirleyemeyip "Intel için üretilmiş / Rosetta desteği bitiyor"
# uyarısı basıyor (2026-07-13 tespiti). Stub yalnızca hrma_baslat.sh'ı çağırır.
if [ ! -f "$B/hrma_stub" ] || [ "$B/hrma_stub.c" -nt "$B/hrma_stub" ]; then
    clang -arch arm64 -O2 -o "$B/hrma_stub" "$B/hrma_stub.c"
fi
cp "$B/hrma_stub" "$APP/Contents/MacOS/HRMA"
chmod +x "$APP/Contents/MacOS/HRMA"

cat > "$APP/Contents/MacOS/hrma_baslat.sh" <<'MAIN'
#!/bin/bash
set -u
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_BUNDLE="$(dirname "$(dirname "$SELF_DIR")")"
RES="$APP_BUNDLE/Contents/Resources"

find_real_app() {
  local CAND
  for CAND in "/Applications/HRMA.app" "$HOME/Applications/HRMA.app" \
              "$HOME/Desktop/HRMA.app" "$HOME/Downloads/HRMA.app"; do
    if [ -d "$CAND" ]; then echo "$CAND"; return 0; fi
  done
  mdfind "kMDItemFSName == 'HRMA.app'" 2>/dev/null | grep -v AppTranslocation | head -1
}

# DMG içinden veya translocation altından çalıştırıldıysa gerçek kopyaya yönlen
case "$APP_BUNDLE" in
  *AppTranslocation*|/Volumes/*)
    REAL="$(find_real_app)"
    if [ -n "$REAL" ] && [ -d "$REAL" ] && [ "$REAL" != "$APP_BUNDLE" ]; then
      xattr -dr com.apple.quarantine "$REAL" 2>/dev/null || true
      exec open -n "$REAL"
    fi
    osascript -e 'display dialog "Lütfen önce HRMA simgesini Applications (Uygulamalar) klasörüne sürükleyin, sonra oradan açın." buttons {"Tamam"} with icon caution with title "HRMA Kurulum"' >/dev/null 2>&1
    exit 1
    ;;
esac

# İlk onaydan sonra karantinayı temizle (sonraki açılışlar sorunsuz olsun).
# DİKKAT (2026-07-14): xattr -dr 1.4 GB'lık ağacın tamamını tarıyor ve
# açılışı DAKİKALARCA bloklayabiliyordu. Artık yalnızca bundle kökünde
# karantina işareti varsa ve ARKA PLANDA çalışır; açılışı bekletmez.
if xattr -p com.apple.quarantine "$APP_BUNDLE" >/dev/null 2>&1; then
  ( xattr -dr com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true ) &
fi

PY="$RES/python/bin/python3.12"
LAUNCH="$RES/app/launcher.py"

LOGDIR="$HOME/Library/Logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/HRMA.log"

# ÖN PLANDA çalıştır (2026-07-14): pencereyi launcher pywebview ile süreç
# içinde açar; süreç = uygulama ömrü. Splash shim'i sayesinde pencere
# saniyeler içinde görünür, ağır importlar arkada yüklenir.
export PYTHONUNBUFFERED=1
exec "$PY" "$LAUNCH" >> "$LOG" 2>&1
MAIN
chmod +x "$APP/Contents/MacOS/hrma_baslat.sh"

echo "[2/7] Python runtime..."
tar -xzf "$B/runtime/pbs-mac.tar.gz" -C "$RES"   # 'python/' kökünü açar

echo "[3/7] libs..."
cp -R "$B/mac/libs" "$RES/libs"
# rocketcea: PyPI'da mac wheel yok — çalışan anaconda ortamından kopyala (arm64, numpy 1.26.4 uyumlu)
cp -R /opt/anaconda3/lib/python3.12/site-packages/rocketcea "$RES/libs/"
cp -R /opt/anaconda3/lib/python3.12/site-packages/rocketcea-*.dist-info "$RES/libs/" 2>/dev/null || true

# pywebview (yerel WKWebView penceresi) + pyobjc ailesi — marker sorunu
# yüzünden --no-deps + açık liste (bkz. build_win_payload.sh notu).
# mac/libs eski bir kopyadan geliyorsa bile bu adım güncel tutar.
python3 -m pip install --target "$RES/libs" --no-deps --only-binary=:all: \
    --upgrade \
    pywebview==6.2.1 bottle==0.13.4 \
    pyobjc-core==12.2.1 pyobjc-framework-Cocoa==12.2.1 \
    pyobjc-framework-Quartz==12.2.1 pyobjc-framework-Security==12.2.1 \
    pyobjc-framework-UniformTypeIdentifiers==12.2.1 \
    pyobjc-framework-WebKit==12.2.1 \
    --no-warn-script-location
# proxy_tools: yalnız sdist (saf Python) → --only-binary'siz ayrı kurulur
python3 -m pip install --target "$RES/libs" --no-deps --upgrade \
    proxy_tools==0.1.0 --no-warn-script-location

# Doğrulama: pywebview'in JS varlıkları olmadan pencere açılışta çöker
# (OC_PythonException: Cannot find JS directory — 2026-07-14 vakası)
[ -d "$RES/libs/webview/js" ] || { echo "HATA: webview/js eksik!"; exit 1; }
[ -d "$RES/libs/reportlab" ] || { echo "HATA: reportlab eksik!"; exit 1; }

echo "[4/7] Uygulama kaynakları..."
mkdir -p "$RES/app"
rsync -a --exclude='__pycache__' "$SRC/hrma" "$RES/app/"
rsync -a "$SRC/data" "$RES/app/"
cp "$B/launcher.py" "$RES/app/launcher.py"
cp "$SRC/icon.icns" "$RES/icon.icns"

echo "[5/7] Temizlik..."
rm -rf "$RES/libs/bin" 2>/dev/null || true   # --target'ın script stub'ları gereksiz (kaleido hariç — kontrol edilecek)

echo "[6/7] Bytecode ön-derleme (ilk açılışı hızlandırır)..."
# Paketin KENDİ python'u ile derle (magic number uyumu garanti).
# __pycache__ silinmiyor — ilk açılışta pandas/scipy derleme bedeli kalkar.
"$RES/python/bin/python3.12" -m compileall -q -j 0 "$RES/libs" "$RES/app" || true

# Bundle seviyesinde ad-hoc imza (arm64 exec ile tutarlı mühür)
codesign --force -s - "$APP" 2>/dev/null || true

echo "[7/7] Boyut:"
du -sh "$APP"
echo "TAMAM: $APP (v$VERSION)"
