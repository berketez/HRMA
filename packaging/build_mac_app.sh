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
    <!-- Ana çalıştırılabilir script olduğu için LaunchServices pencere kaydı
         beklemesin: Dock'ta sonsuz zıplama bunun yüzündendi (2026-07-13) -->
    <key>LSUIElement</key><true/>
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

# İlk onaydan sonra karantinayı temizle (sonraki açılışlar sorunsuz olsun)
xattr -dr com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true

PY="$RES/python/bin/python3.12"
LAUNCH="$RES/app/launcher.py"

# Terminal'siz başlatma (2026-07-13): sunucu arka planda, log dosyaya.
# UI penceresini launcher kendisi açar (Chromium --app, ayrı profil) ve
# pencere kapanınca sunucu da kapanır — gerçek uygulama davranışı.
LOGDIR="$HOME/Library/Logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/HRMA.log"

# Zaten çalışıyorsa launcher 'already running' dalında yalnız pencere açar
export PYTHONUNBUFFERED=1
"$PY" "$LAUNCH" >> "$LOG" 2>&1 &
disown

# 75 sn'ye kadar sunucunun kalkmasını bekle; kalkmazsa kullanıcıya söyle
for i in $(seq 1 75); do
  for p in 8080 8081 8082 8083 8084; do
    if curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$p/"; then
      exit 0
    fi
  done
  sleep 1
done
osascript -e 'display dialog "HRMA başlatılamadı. Ayrıntı için şu dosyaya bakın: Kitaplık/Logs/HRMA.log" buttons {"Tamam"} with icon caution with title "HRMA"' >/dev/null 2>&1
exit 1
MAIN
chmod +x "$APP/Contents/MacOS/hrma_baslat.sh"

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

# Bundle seviyesinde ad-hoc imza (arm64 exec ile tutarlı mühür)
codesign --force -s - "$APP" 2>/dev/null || true

echo "[6/6] Boyut:"
du -sh "$APP"
echo "TAMAM: $APP"
