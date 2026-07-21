"""Sessiz otomatik kurulum — indirilen güncellemeyi kullanıcı dokunmadan kurar.

update_checker indirmeyi bitirdikten sonra arayüz /api/update/install'ı
çağırır; burada kurulu hedef tespit edilir, platforma özgü bir yardımcı
betik bağımsız süreç olarak başlatılır ve uygulama kendini kapatır:

- macOS: yardımcı bash betiği uygulamanın kapanmasını bekler, DMG'yi
  hdiutil ile bağlar, içindeki .app'i ditto ile hedefin YANINA kopyalar
  (aynı APFS bölümü → mv = anlık adlandırma), eskiyi kenara alıp yenisini
  yerine oturtur, yeni sürümün gerçekten AÇILDIĞINI doğrulayana kadar
  eskiyi SİLMEZ (açılmazsa geri yükler). Sürükle-bırak ve "değiştirilsin
  mi?" penceresi tamamen ortadan kalkar.
- Windows: yardımcı .bat betiği uygulamanın kapanmasını bekler, NSIS
  kurucusunu sessiz modda (/S) MEVCUT kurulum dizinine (/D=) çalıştırır
  ve HRMA'yı yeniden başlatır. Kurucu, sessiz modda çalışan HRMA
  süreçlerini zaten kendisi kapatır (packaging/hrma.nsi).

Kaynak koddan (start.sh / python app.py) çalışırken, hedef yazılabilir
değilken, disk alanı yetersizken ya da uygulama DMG içinden/karantina
kopyasından (App Translocation) çalışıyorken "manual" moda düşülür:
eski davranış (kurulum dosyasını işletim sistemine açtırmak) korunur.

Güvenlik: kurulacak dosya yolu İSTEMCİDEN ALINMAZ — update_checker'ın
kendi indirdiği, boyutu ve (GitHub API digest verdiyse) SHA-256 özeti
doğrulanmış dosya kullanılır. 2026-07-21 codex risk denetimi bulguları
uygulanmıştır (yazma probu, translocation bekçisi, disk alanı, detach
retry, staging bütünlüğü, relaunch doğrulaması + geri yükleme).
"""

import os
import re
import sys
import time
import shutil
import tempfile
import threading
import subprocess

import hrma

# Yardımcı betik günlüğü kullanıcının görebileceği bir yere yazılır
# (launcher'ın hrma_log.txt dosyasıyla aynı dizin: Belgeler/HRMA).
UPDATE_LOG_NAME = "hrma_update_log.txt"

# macOS'ta kurulum için gereken boş alan: sıkıştırılmış DMG'nin ~4.5 katı
# uygulama + geçici staging kopyası. Güvenli pay ile 6x istenir.
MAC_FREE_SPACE_FACTOR = 6

# Batch betiğine gömüldüğünde cmd.exe tarafından özel yorumlanan
# karakterler; kurulum yolunda görülürse otomatik moda GİRİLMEZ
# (pratikte yalnızca sıra dışı kullanıcı adlarında olur).
_CMD_UNSAFE = re.compile(r"[&^%!<>|()\"]")


def _package_root():
    """hrma paketinin kurulu olduğu dizin (…/app/hrma)."""
    return os.path.dirname(os.path.abspath(hrma.__file__))


def _log_dir():
    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    base = docs if os.path.isdir(docs) else home
    out = os.path.join(base, "HRMA")
    try:
        os.makedirs(out, exist_ok=True)
        return out
    except OSError:
        return tempfile.gettempdir()


def _helper_dir(plan):
    """Yardımcı betiğin yazılacağı KALICI dizin.

    /tmp kullanılmaz: macOS geçici dizin temizliği ve Windows'ta antivirüs
    %TEMP% şüpheciliği, betiği çalışırken silebilir (codex bulgusu).
    Windows'ta INSTDIR/updater güvenlidir: kurucu yalnız app/libs/python
    dizinlerini siler, NSIS süreç-kapatma filtresi de cmd.exe'yi görmez
    (ExecutablePath System32'dir).
    """
    if plan["platform"] == "darwin":
        d = os.path.expanduser("~/Library/Application Support/HRMA/updater")
    else:
        d = os.path.join(plan["target"], "updater")
    os.makedirs(d, exist_ok=True)
    return d


def _dir_writable(path):
    """os.access yerine GERÇEK yazma probu (macOS ACL/SIP'te access yanılır)."""
    try:
        fd, probe = tempfile.mkstemp(prefix=".hrma-w-", dir=path)
        os.close(fd)
        os.remove(probe)
        return True
    except OSError:
        return False


def find_mac_bundle(start_path=None):
    """hrma paketinden yukarı yürüyerek kurulu .app kökünü bulur.

    Paket .app içinde Contents/Resources/app/hrma konumundadır. Gerçek bir
    uygulama paketi olduğundan emin olmak için Contents/MacOS dizini aranır.
    Kaynak koddan çalışılıyorsa None döner.
    """
    path = os.path.abspath(start_path or _package_root())
    for _ in range(12):
        if path.endswith(".app") and os.path.isdir(
                os.path.join(path, "Contents", "MacOS")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return None


def find_win_install_dir(start_path=None):
    """hrma paketinden Windows kurulum dizinini (NSIS $INSTDIR) bulur.

    Yerleşim: <INSTDIR>/app/hrma — doğrulama için kurucunun bıraktığı
    python/pythonw.exe ve uninstall.exe aranır. Kaynak koddan (git deposu)
    çalışılıyorsa bu dosyalar olmadığından None döner.
    """
    pkg = os.path.abspath(start_path or _package_root())
    instdir = os.path.dirname(os.path.dirname(pkg))
    if (os.path.isfile(os.path.join(instdir, "python", "pythonw.exe"))
            and os.path.isfile(os.path.join(instdir, "app", "launcher.py"))
            and os.path.isfile(os.path.join(instdir, "uninstall.exe"))):
        return instdir
    return None


def plan_install(installer_path, platform=None, start_path=None,
                 installer_size=None):
    """Otomatik kurulum yapılıp yapılamayacağına karar verir.

    Dönüş: {"mode": "auto", ...} ya da {"mode": "manual", "reason": ...}.
    "manual" hata değildir — çağıran, eski davranışa (kurulum dosyasını
    işletim sistemine açtırmaya) düşer.
    """
    platform = platform or sys.platform
    if platform == "darwin":
        if not installer_path.lower().endswith(".dmg"):
            return {"mode": "manual", "reason": "installer is not a dmg"}
        target = find_mac_bundle(start_path)
        if not target:
            return {"mode": "manual",
                    "reason": "not running from an installed .app bundle"}
        # Gatekeeper App Translocation / DMG içinden çalıştırma: gerçek
        # kurulum yolu bu değildir, üzerine yazmak anlamsız/imkansız.
        real = os.path.realpath(target)
        if "/AppTranslocation/" in real or real.startswith("/Volumes/"):
            return {"mode": "manual",
                    "reason": "application runs from a translocated/DMG copy"}
        parent = os.path.dirname(target)
        # Takas iki adlandırmadan ibaret — ikisi de ÜST dizinde yazma ister.
        if not _dir_writable(parent):
            return {"mode": "manual",
                    "reason": "application folder is not writable"}
        try:
            free = shutil.disk_usage(parent).free
        except OSError:
            free = None
        need = MAC_FREE_SPACE_FACTOR * (
            installer_size or _safe_size(installer_path))
        if free is not None and need and free < need:
            return {"mode": "manual",
                    "reason": "not enough free disk space for staging"}
        return {"mode": "auto", "platform": "darwin", "target": target}

    if platform in ("win32", "cygwin"):
        if not installer_path.lower().endswith(".exe"):
            return {"mode": "manual", "reason": "installer is not an exe"}
        instdir = find_win_install_dir(start_path)
        if not instdir:
            return {"mode": "manual",
                    "reason": "not running from an installed copy"}
        if _CMD_UNSAFE.search(instdir) or _CMD_UNSAFE.search(installer_path):
            # cmd.exe'ye gömülemeyecek karakterli yol — betik bozulur
            return {"mode": "manual",
                    "reason": "install path contains characters unsafe for cmd"}
        if not _dir_writable(instdir):
            return {"mode": "manual",
                    "reason": "install folder is not writable"}
        return {"mode": "auto", "platform": "win32", "target": instdir}

    return {"mode": "manual", "reason": "unsupported platform: %s" % platform}


def _safe_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Yardımcı betikler
# ---------------------------------------------------------------------------

# macOS: yollar betiğe GÖMÜLMEZ, argüman olarak geçer (tırnak/boşluk
# sorunlarını kökten keser). Sıra: PID DMG HEDEF LOG.
# Akış: bekle → bağla → staging'e kopyala → doğrula → takas → yeni sürüm
# GERÇEKTEN AÇILANA KADAR eskiyi tut → açılmazsa geri yükle.
MAC_HELPER = r"""#!/bin/bash
# HRMA otomatik guncelleme yardimcisi - update_checker tarafindan uretilir.
PID="$1"; DMG="$2"; TARGET="$3"; LOG="$4"
cd /
exec >>"$LOG" 2>&1
echo "=== HRMA update helper started: $(date) ==="
echo "pid=$PID dmg=$DMG target=$TARGET"

MNT=""

fallback() {
    echo "FALLBACK: $1 - opening the DMG for manual installation"
    if [ -n "$MNT" ]; then hdiutil detach "$MNT" -force >/dev/null 2>&1; fi
    open "$DMG"
    exit 1
}

detach_dmg() {
    # Spotlight/quicklookd mount'u kisa sure mesgul tutabilir - sabirli ol
    for _ in 1 2 3 4; do
        hdiutil detach "$MNT" >/dev/null 2>&1 && MNT="" && return 0
        sleep 2
    done
    hdiutil detach "$MNT" -force >/dev/null 2>&1
    MNT=""
}

# 1) Uygulamanin kapanmasini bekle (en cok 90 sn). PID yeniden kullanima
#    karsi komut satiri da dogrulanir: bizim bundle degilse olmus sayilir.
for _ in $(seq 1 90); do
    CMD="$(ps -p "$PID" -o command= 2>/dev/null)"
    [ -z "$CMD" ] && break
    case "$CMD" in
        *"$TARGET"*) sleep 1 ;;
        *) break ;;
    esac
done
CMD="$(ps -p "$PID" -o command= 2>/dev/null)"
case "$CMD" in
    *"$TARGET"*) fallback "application did not exit in time" ;;
esac
sleep 1  # dosya tanitici birakma payi

# 2) DMG'yi baglan
MNT="$(mktemp -d /tmp/hrma-update-XXXXXX)" || { MNT=""; fallback "mktemp failed"; }
hdiutil attach -nobrowse -noverify -noautoopen -readonly \
    -mountpoint "$MNT" "$DMG" || fallback "hdiutil attach failed"

SRC=""
for cand in "$MNT"/*.app; do
    [ -d "$cand" ] && SRC="$cand" && break
done
[ -z "$SRC" ] && fallback "no .app found inside the dmg"

# 3) Hedefin YANINA kopyala (ayni disk bolumu -> mv = anlik adlandirma)
PARENT="$(dirname "$TARGET")"
BASE="$(basename "$TARGET")"
STAGING="$PARENT/.$BASE.update.$$"
OLD="$PARENT/.$BASE.old.$$"
rm -rf "$STAGING"
if ! ditto "$SRC" "$STAGING"; then
    rm -rf "$STAGING"
    fallback "copy (ditto) failed"
fi
detach_dmg

# 3b) Staging butunlugu: yarim kopyayla takas YAPILMAZ
if [ ! -d "$STAGING/Contents/MacOS" ] || \
   [ ! -d "$STAGING/Contents/Resources/app/hrma" ]; then
    rm -rf "$STAGING"
    fallback "staged copy is incomplete"
fi

# 4) Anlik degisim: eskiyi kenara al, yeniyi oturt; olmazsa geri al
if ! mv "$TARGET" "$OLD"; then
    rm -rf "$STAGING"
    fallback "could not move the old application aside"
fi
if ! mv "$STAGING" "$TARGET"; then
    mv "$OLD" "$TARGET"
    rm -rf "$STAGING"
    fallback "could not move the new application into place"
fi

# 5) Karantina temizligi (savunmaci) + yeniden baslat
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
open "$TARGET"

# 6) Yeni surum GERCEKTEN acildi mi? Acilmadiysa eskiyi geri yukle.
#    (grep -F: yol regex degil sabit metin olarak aranir)
STARTED=""
for _ in $(seq 1 20); do
    sleep 1
    if ps ax -o command= | grep -F "$TARGET/" | grep -v grep >/dev/null; then
        STARTED=1
        break
    fi
done
if [ -z "$STARTED" ]; then
    echo "new version did not start - restoring the previous version"
    rm -rf "$TARGET"
    mv "$OLD" "$TARGET"
    open "$TARGET"
    fallback "update failed, previous version restored"
fi
rm -rf "$OLD"
echo "=== HRMA update complete: $(date) ==="
"""

# Windows: cmd.exe argüman aktarımı kırılgan olduğundan yollar betiğe
# gömülür; plan_install gömülemeyecek karakterleri zaten elemiştir.
# NSIS kuralları: /S sessiz kurulum; /D= MUTLAK SON parametredir ve
# boşluk içerse bile TIRNAKSIZ yazılır (NSIS satır sonuna kadar okur).
# Kurucu batch icinden dogrudan cagrilir (start KULLANILMAZ — bosluklu
# yollarda baslik/arguman ayristirmasi tuzakli; batch zaten bekler).
WIN_HELPER = """@echo off
title HRMA Update
cd /d "%TEMP%"
echo.
echo   Updating HRMA to the new version...
echo   HRMA will reopen automatically when the update is complete.
echo   Please do not close this window.
echo.
powershell -NoProfile -Command "Wait-Process -Id {pid} -Timeout 90 -ErrorAction SilentlyContinue" >nul 2>&1
"{setup}" /S /D={instdir}
if not exist "{instdir}\\python\\pythonw.exe" (
  echo   Silent install failed - starting the normal installer instead.
  start "" "{setup}"
  exit /b 1
)
start "" "{instdir}\\python\\pythonw.exe" "{instdir}\\app\\launcher.py"
(goto) 2>nul & del "%~f0"
"""


def build_win_helper(pid, setup_path, instdir):
    return WIN_HELPER.format(pid=int(pid), setup=setup_path, instdir=instdir)


def _write_helper(plan, content, suffix):
    path = os.path.join(_helper_dir(plan), "hrma_update" + suffix)
    # Batch dosyaları cmd.exe'nin yerel kod sayfasıyla okunur; içerik ASCII
    # tutulur (betiklerde Türkçe karakter kullanılmaz).
    with open(path, "w", encoding="ascii", newline="") as f:
        f.write(content)
    return path


def launch_helper(plan, installer_path, pid=None):
    """Yardımcı betiği yazar ve bağımsız süreç olarak başlatır.

    Başarıda {"launched": True, "log": ...}; hata fırlatmaz, sorun varsa
    {"launched": False, "error": ...} döner (çağıran manuel moda düşer).
    """
    pid = pid or os.getpid()
    log_path = os.path.join(_log_dir(), UPDATE_LOG_NAME)
    try:
        if plan["platform"] == "darwin":
            script = _write_helper(plan, MAC_HELPER, ".sh")
            subprocess.Popen(
                ["/bin/bash", script, str(pid), installer_path,
                 plan["target"], log_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, cwd="/",
            )
        else:
            script = _write_helper(
                plan, build_win_helper(pid, installer_path, plan["target"]),
                ".bat")
            # Görünür küçük bir konsol: sessiz kurulum 1-2 dk sürer, kullanıcı
            # "uygulama yok oldu" sanmasın. CREATE_NEW_CONSOLE süreci bizim
            # konsolumuzdan da ayırır; uygulama kapanınca yardımcı yaşar.
            subprocess.Popen(
                ["cmd.exe", "/c", script],
                creationflags=(subprocess.CREATE_NEW_CONSOLE
                               | subprocess.CREATE_NEW_PROCESS_GROUP),
                close_fds=True,
            )
        return {"launched": True, "log": log_path}
    except Exception as exc:
        return {"launched": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def schedule_app_exit(delay_s=1.2):
    """Uygulamayı kısa gecikmeyle kapatır (HTTP yanıtı önce gitsin).

    Önce pywebview penceresi nazikçe kapatılır — launcher'ın ana thread'i
    webview.start dönüşünde zaten os._exit(0) yapar. Pencere yoksa ya da
    kapanış takılırsa süreç güvence olarak burada sonlandırılır.
    """
    def _bye():
        time.sleep(delay_s)
        try:
            import webview
            for w in list(getattr(webview, "windows", []) or []):
                try:
                    w.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(1.5)
        os._exit(0)

    threading.Thread(target=_bye, daemon=True).start()
