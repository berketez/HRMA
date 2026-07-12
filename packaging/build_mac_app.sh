#!/bin/bash
# HRMA.app + DMG kurucu (macOS arm64)
set -euo pipefail

B="$(cd "$(dirname "$0")" && pwd)"
SRC="/Users/apple/Desktop/dosyalar/HRMA"
APP="$B/mac/HRMA.app"
RES="$APP/Contents/Resources"

echo "[1/6] İskelet..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>HRMA</string>
    <key>CFBundleDisplayName</key><string>HRMA</string>
    <key>CFBundleIdentifier</key><string>com.uzaytek.hrma</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleShortVersionString</key><string>1.0.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>HRMA</string>
    <key>CFBundleIconFile</key><string>icon.icns</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/HRMA" <<'MAIN'
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

# İlk onaydan sonra karantinayı temizle (sonraki açılışlar sorunsuz olsun)
xattr -dr com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true

PY="$RES/python/bin/python3.12"
LAUNCH="$RES/app/launcher.py"

# Terminal yalnızca .command uzantılı dosyaları çalıştırıyor (2026-07-13 tespiti)
RUNNER="$(mktemp /tmp/hrma-run-XXXXXX)"
mv "$RUNNER" "$RUNNER.command"
RUNNER="$RUNNER.command"
cat > "$RUNNER" <<EOF
#!/bin/bash
clear
exec "$PY" "$LAUNCH"
EOF
chmod +x "$RUNNER"
exec open -a Terminal "$RUNNER"
MAIN
chmod +x "$APP/Contents/MacOS/HRMA"

echo "[2/6] Python runtime..."
tar -xzf "$B/runtime/pbs-mac.tar.gz" -C "$RES"   # 'python/' kökünü açar

echo "[3/6] libs..."
cp -R "$B/mac/libs" "$RES/libs"
# rocketcea: PyPI'da mac wheel yok — çalışan anaconda ortamından kopyala (arm64, numpy 1.26.4 uyumlu)
cp -R /opt/anaconda3/lib/python3.12/site-packages/rocketcea "$RES/libs/"
cp -R /opt/anaconda3/lib/python3.12/site-packages/rocketcea-*.dist-info "$RES/libs/" 2>/dev/null || true

echo "[4/6] Uygulama kaynakları..."
mkdir -p "$RES/app"
rsync -a --exclude='__pycache__' "$SRC/hrma" "$RES/app/"
rsync -a "$SRC/data" "$RES/app/"
cp "$B/launcher.py" "$RES/app/launcher.py"
cp "$SRC/icon.icns" "$RES/icon.icns"

echo "[5/6] Temizlik..."
find "$RES/libs" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$RES/libs/bin" 2>/dev/null || true   # --target'ın script stub'ları gereksiz (kaleido hariç — kontrol edilecek)

echo "[6/6] Boyut:"
du -sh "$APP"
echo "TAMAM: $APP"
