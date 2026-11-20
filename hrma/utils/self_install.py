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

# ---------------------------------------------------------------------------
# Güncelleme kilidi (V306/GÜNCELLEME kalem 1) — TEK KAYNAK
#
# KUSUR (15 Eki 2026, 2.6.26 → 3.0.0, Berke): güncelleme ~4 dk sürüyor;
# kullanıcı bu sırada HRMA'yı açınca hedefte hâlâ ESKİ paket durduğu için eski
# sürüm açıldı ve "güncelleme bozuk" sanıldı. Açılış engellenmiyordu.
#
# Çözüm: macOS yardımcı betiği başlarken kilit dosyası yazar, her çıkış
# yolunda (başarı, geri yükleme, fallback, sinyal) ``trap … EXIT`` ile
# kaldırır. Açılış (packaging/launcher.py) kilidi okur; kilit geçerliyse
# sunucuyu başlatmaz, "güncelleme sürüyor" penceresini gösterir.
#
# SÖZLEŞME SÜRÜMLER ARASIDIR: kilidi KURULU ESKİ sürümün betiği yazar, yeni
# sürümün açılışı da okuyabilir. Bu yüzden biçim sabit ve geriye uyumludur:
# ilk satır başlık, sonra ``anahtar=değer`` satırları, EN SONDA ``target=``
# (yol satır sonu içerse bile dosya sonuna kadar okunur). Bilinmeyen anahtar
# yok sayılır; bilinmeyen aşama "bekle" sayılır (yaş sınırıyla bağlı).
#
# FAIL-SAFE: kilit uygulamayı asla kalıcı olarak açılmaz hâle getiremez.
# Betik süreci ölmüşse, PID başka bir programa geçmişse ya da kilit yaşı
# üst sınırı aşmışsa kilit BAYATTIR: kaldırılır, güncelleme günlüğüne
# yazılır ve uygulama normal açılır.
# ---------------------------------------------------------------------------

#: Kilit dosyasının adı; yeri güncelleme günlüğünün dizini (:func:`_log_dir`).
UPDATE_LOCK_NAME = "hrma_update.lock"

#: Kilit biçiminin ilk satırı (biçim değişirse sürüm numarası artar).
UPDATE_LOCK_HEADER = "hrma-update-lock 1"

#: Okunacak en büyük kilit dosyası (bayt). Gerçek kilit ~300 bayttır; daha
#: büyüğü bozuk/yabancı dosyadır ve bayat sayılır.
UPDATE_LOCK_MAX_BYTES = 64 * 1024

#: Kilit yaşı üst sınırı (s) — HRMA SEÇİMİ. Ölçülen gerçek güncelleme süresi
#: ~3 dk 50 sn (``~/Documents/HRMA/hrma_update_log.txt``: 15 Eki 23:08:46 →
#: 23:12:38 ve 28 Eki 23:59:48 → 00:03:38; kopya adımı tek başına 2 dk 38 sn
#: – 2 dk 51 sn). Yavaş disk / eski Mac için 5 kat pay → 20 dk. Bu süreyi
#: aşan kilit, betik yaşasa bile bayat sayılır (açılış kalıcı engellenemez).
UPDATE_LOCK_MAX_AGE_S = 20 * 60

#: Başlama zamanı gelecekteyse (saat geri alındı / bozuk değer) kabul edilen
#: en büyük sapma (s); aşan kilit bayat.
UPDATE_LOCK_FUTURE_SLACK_S = 60

#: Yardımcı betiğin dosya adı kökü; PID yeniden kullanımına karşı kilitteki
#: PID'in komut satırında bu ad aranır.
HELPER_SCRIPT_STEM = "hrma_update"

#: Kopya ilerlemesi ölçüm aralığı (s, TAMSAYI) — HRMA SEÇİMİ. Her ölçüm staging
#: ağacında ``du -sk`` koşar; 62 595 dosyalık sentetik kopyada 0,32-0,33 sn
#: ölçüldü (docs/scofield/raw/OH/V306/guncelleme/olcum_kalem3.json). 3 sn
#: aralık bir çekirdeğin ~%10'u; ~2,7 dk'lık kopyada ~50 gerçek ölçüm.
HELPER_PROGRESS_INTERVAL_S = 3

#: Kapanış adımında hedef paketten çalışan HRMA süreçlerinin kendiliğinden
#: kapanması için beklenen süre (s) — HRMA SEÇİMİ. Bekleme penceresi kilidi
#: 0,5 sn'de bir yoklar (launcher GUNCELLEME_YOKLAMA_S) ve "closing" aşamasını
#: görünce kapanır; 10 sn ≈ 20 yoklama payı. Süre dolunca SIGTERM.
HELPER_CLOSE_WAIT_S = 10

#: SIGTERM sonrası kapanma payı (s) — HRMA SEÇİMİ; kapanmazsa takas YAPILMAZ.
HELPER_TERM_WAIT_S = 5

#: Açılış doğrulamasının toplam süresi (s) — eski betikteki değer (20 × 1 sn).
HELPER_LAUNCH_VERIFY_S = 20

#: Bu süre sonunda yeni süreç görünmediyse ``open`` bir kez daha çağrılır (s).
HELPER_REOPEN_AFTER_S = 10

#: Yeni sürecin "açıldı" sayılması için yaşaması gereken süre (s) — HRMA
#: SEÇİMİ: anında çöken süreç başarı sayılmaz.
HELPER_LAUNCH_STABLE_S = 2

#: Betiğin, güncellemeyi isteyen uygulamanın kapanmasını beklediği en uzun
#: süre (s) — eski betikteki değer (``seq 1 90``, 1 sn aralık). Pencere bu
#: süreyi hata metninde adıyla söyler.
HELPER_EXIT_WAIT_S = 90

# ---------------------------------------------------------------------------
# Güncelleme penceresi (V307/GÜNCELLEME-EKRAN) — TEK KAYNAK
#
# KUSUR (10 Kas 2026, 3.0.5 → 3.0.6, Berke): "HRMA yüklendi" düğmesinden sonra
# uygulama kapanıyor, yeni sürüm açılana kadar (~3,5 dk; güncelleme günlüğü
# 14:44:38 → 14:48:12) ekranda HİÇBİR ŞEY olmuyordu; tek iz birkaç saniyede
# kaybolan bir sistem bildirimiydi. Kullanıcı kurulumun sürdüğünü, takıldığını
# ya da bittiğini ayırt edemiyordu.
#
# Çözüm: yardımcı betik başlarken uygulama paketinden BAĞIMSIZ bir pencere
# süreci açar — macOS'ta /usr/bin/osascript (JXA + AppKit), Windows'ta
# PowerShell + WinForms. İkisi de işletim sisteminin parçasıdır; kurulum
# sırasında silinen/değiştirilen paket içi Python'a bağlı DEĞİLDİR. Pencere
# betiği kurulumdan ÖNCE yardımcı betiğin yanına yazılır (hrma/utils/
# update_window.py).
#
# DURUM SÖZLEŞMESİ: pencere yalnız betiğin yazdığı durum dosyasını okur
# (``UPDATE_STATUS_NAME``, betiğin yanında): ilk satır başlık, sonra
# ``anahtar=değer`` satırları, SON satır ``end=1`` (yarım yazılmış dosya
# okunmaz). Alanlar: pid, started, step, phase, done_kb, total_kb, lang,
# from_version, to_version, result, error. Yol yoktur; yollar pencereye
# argümanla gider. Adım/oran yalnız betiğin gerçekten bildiği durumdan;
# zamana bağlı ya da uydurma ilerleme YOK.
# ---------------------------------------------------------------------------

#: Durum dosyasının adı; yeri yardımcı betiğin dizini (:func:`_helper_dir`).
UPDATE_STATUS_NAME = "hrma_update_status.txt"

#: Durum dosyası biçiminin ilk satırı (biçim değişirse sürüm numarası artar).
UPDATE_STATUS_HEADER = "hrma-update-status 1"

#: Okunacak en büyük durum dosyası (bayt). Gerçek dosya ~250 bayttır; daha
#: büyüğü bozuk/yabancı dosyadır ve okunmaz.
UPDATE_STATUS_MAX_BYTES = 64 * 1024

#: Pencere betiklerinin adları (yardımcı betiğin yanında).
UPDATE_WINDOW_MAC_NAME = HELPER_SCRIPT_STEM + "_window.js"
UPDATE_WINDOW_WIN_NAME = HELPER_SCRIPT_STEM + "_window.ps1"

#: Sonuç değerleri: running — sürüyor; ok — yeni sürüm açıldı; failed —
#: tamamlanamadı (önceki sürüm yerinde); restored — yeni sürüm açılmadı,
#: önceki sürüm geri yüklendi.
UPDATE_RESULT_RUNNING = "running"
UPDATE_RESULT_OK = "ok"
UPDATE_RESULT_FAILED = "failed"
UPDATE_RESULT_RESTORED = "restored"
UPDATE_RESULTS = (UPDATE_RESULT_RUNNING, UPDATE_RESULT_OK,
                  UPDATE_RESULT_FAILED, UPDATE_RESULT_RESTORED)

#: Hata kodu → kullanıcının ne yapacağı (pencere metni ``window.action.*``).
#: Betikler yalnız bu kodları yazar; ``helper_gone`` pencerenin kendi
#: tespitidir (betik sonuç yazmadan öldü).
UPDATE_ERROR_ACTIONS = {
    "app_not_closed": "mac_opened",
    "mktemp_failed": "mac_opened",
    "mount_failed": "redownload",
    "no_app_in_dmg": "redownload",
    "copy_failed": "mac_opened",
    "staged_incomplete": "mac_opened",
    "instance_running": "mac_opened",
    "swap_failed": "mac_opened",
    "new_version_not_started": "mac_restored",
    "interrupted": "manual",
    "unexpected": "manual",
    "helper_gone": "manual",
    "silent_install_failed": "win_opened",
}

#: Pencerenin durum dosyasını yoklama aralığı (s) — HRMA SEÇİMİ; açılışın
#: bekleme penceresiyle aynı tempo (packaging/launcher.py
#: GUNCELLEME_YOKLAMA_S). Okunan dosya ~250 bayt; maliyet ihmal edilebilir.
HELPER_WINDOW_POLL_S = 0.5

#: Başarıdan sonra pencerenin kendiliğinden kapanma gecikmesi (s) — HRMA
#: SEÇİMİ: "tamamlandı" satırı okunabilsin, yeni sürümün penceresini
#: örtmesin.
HELPER_WINDOW_DONE_CLOSE_S = 3

#: Pencerede gösterilen sürüm alanı için izinli biçim (betiğe ve dosyaya
#: yalnız bu biçim yazılır; uymayan değer boş kalır, sürüm satırı gizlenir).
_VERSION_SAFE_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,31}")


def safe_version(value):
    """Sürüm dizesi izinli biçimdeyse kendisi, değilse '' (sessiz uydurma yok:
    bilinmeyen sürüm pencerede gösterilmez)."""
    return value if isinstance(value, str) and _VERSION_SAFE_RE.fullmatch(
        value) else ""


#: Kilit aşamaları (betik yazar, açılış okur):
#:   wait    — kopya/hazırlık sürüyor: açılış bekleme penceresi gösterir,
#:   closing — eski sürüm kapatılıyor / takas: açılış HİÇBİR ŞEY açmadan çıkar
#:             (yeni sürümü betik açar),
#:   launch  — takas bitti, yeni (ya da geri yüklenen) sürüm açılıyor: açılış
#:             normal devam eder.
LOCK_PHASE_WAIT = "wait"
LOCK_PHASE_CLOSING = "closing"
LOCK_PHASE_LAUNCH = "launch"

# Batch betiğine gömüldüğünde cmd.exe tarafından özel yorumlanan
# karakterler; kurulum yolunda görülürse otomatik moda GİRİLMEZ
# (pratikte yalnızca sıra dışı kullanıcı adlarında olur).
#
# SATIR SONU ve diğer denetim karakterleri de kapıya dâhildir (2026-08-27).
# Gerekçe: yol, WIN_HELPER şablonunun İÇİNE gömülüp .bat olarak yazılıyor;
# batch dosyasında satır sonu KOMUT AYRACIDIR, yani '\n' içeren bir yol
# betikte yeni bir satır — yeni bir komut — açardı. Sekme/CR de ayrıştırmayı
# bozar. BUGÜN SÖMÜRÜLEBİLİR DEĞİLDİR: NTFS dosya/dizin adında 0x00-0x1F
# aralığını zaten kabul etmiyor, dolayısıyla böyle bir kurulum yolu
# oluşturulamıyor. Bu yüzden buradaki değişiklik bir açığın kapatılması
# değil, SAVUNMA DERİNLİĞİDİR: kapı, yolun nereden geldiğine (kayıt
# defteri, taşınan kurulum, ileride eklenecek bir kaynak) bağlı kalmasın.
_CMD_UNSAFE = re.compile(r"[&^%!<>|()\"]|[\x00-\x1f]")


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


def update_log_path():
    """Güncelleme günlüğünün yolu (betik ve açılış aynı dosyaya yazar)."""
    return os.path.join(_log_dir(), UPDATE_LOG_NAME)


def update_lock_path():
    """Güncelleme kilidinin yolu: günlüğün dizini (Belgeler/HRMA)."""
    return os.path.join(_log_dir(), UPDATE_LOCK_NAME)


def _int_or_none(v):
    v = (v or "").strip()
    return int(v) if v.isdigit() else None


def read_update_lock(path=None):
    """Kilidi okur. Yoksa None; bozuksa ``{"_error": neden}``; değilse sözlük.

    Alanlar: pid, started (epoch s), step, phase, done_kb, total_kb, lang,
    target. Sayısal alanlar int ya da None'dır; değer uydurulmaz.
    """
    path = path or update_lock_path()
    try:
        with open(path, "rb") as f:
            raw = f.read(UPDATE_LOCK_MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return {"_error": "lock is not readable (%s)" % exc}
    if len(raw) > UPDATE_LOCK_MAX_BYTES:
        return {"_error": "lock is larger than %d bytes" % UPDATE_LOCK_MAX_BYTES}
    text = raw.decode("utf-8", "replace")
    head, sep, target = text.partition("\ntarget=")
    lines = head.split("\n")
    if not lines or lines[0].strip() != UPDATE_LOCK_HEADER:
        return {"_error": "unknown lock format"}
    fields = {}
    for line in lines[1:]:
        k, eq, v = line.partition("=")
        if eq:
            fields[k.strip()] = v
    if sep and target.endswith("\n"):
        target = target[:-1]
    step = fields.get("step", "")
    return {
        "pid": _int_or_none(fields.get("pid")),
        "started": _int_or_none(fields.get("started")),
        "step": step if re.fullmatch(r"[a-z_]{1,32}", step) else None,
        "phase": fields.get("phase", "").strip() or None,
        "done_kb": _int_or_none(fields.get("done_kb")),
        "total_kb": _int_or_none(fields.get("total_kb")),
        "lang": fields.get("lang", "").strip() or None,
        "target": target if sep else None,
    }


def _helper_alive(pid):
    """(yaşıyor_mu, neden). Yalnız POSIX: Windows'ta os.kill(pid, 0)
    CTRL_C_EVENT göndermek demektir, orada bu işlev ÇAĞRILMAZ."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False, "update helper (pid %d) is not running" % pid
    except PermissionError:
        pass  # başka kullanıcının süreci: komut satırıyla karar verilir
    except OSError as exc:
        return False, "update helper (pid %d) cannot be checked: %s" % (pid, exc)
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return True, "helper alive (command line not readable)"
    if not cmd.strip():
        return False, "update helper (pid %d) is not running" % pid
    if HELPER_SCRIPT_STEM not in cmd:
        return False, ("pid %d now belongs to another program (pid reuse)"
                       % pid)
    return True, "helper alive"


def update_lock_decision(path=None, now=None, helper_alive=None):
    """Açılışın kilit kararı.

    Dönüş ``{"decision": d, "reason": str, "lock": dict|None}``; d:
      none   — kilit yok,
      stale  — kilit bayat (çağıran kaldırır ve günlüğe yazar),
      wait   — güncelleme sürüyor: bekleme penceresi,
      exit   — eski sürüm kapatılıyor: hiçbir şey açmadan çık,
      normal — takas bitti, yeni sürüm açılıyor: normal başla.
    """
    if os.name != "posix":
        # Kilidi yalnız macOS betiği yazar; Windows'ta PID denetimi de
        # güvenli değildir (bkz. _helper_alive).
        return {"decision": "none", "reason": "lock check is macOS-only",
                "lock": None}
    lock = read_update_lock(path)
    if lock is None:
        return {"decision": "none", "reason": "no update lock", "lock": None}
    if "_error" in lock:
        return {"decision": "stale", "reason": lock["_error"], "lock": lock}
    pid, started = lock["pid"], lock["started"]
    if not pid or pid <= 1 or started is None:
        return {"decision": "stale", "reason": "lock has no valid pid/start",
                "lock": lock}
    now = time.time() if now is None else now
    if started - now > UPDATE_LOCK_FUTURE_SLACK_S:
        return {"decision": "stale", "reason": "lock start time is in the future",
                "lock": lock}
    if now - started > UPDATE_LOCK_MAX_AGE_S:
        return {"decision": "stale",
                "reason": "lock is older than %d s" % UPDATE_LOCK_MAX_AGE_S,
                "lock": lock}
    alive, why = (helper_alive or _helper_alive)(pid)
    if not alive:
        return {"decision": "stale", "reason": why, "lock": lock}
    if lock["phase"] == LOCK_PHASE_LAUNCH:
        return {"decision": "normal", "reason": "new version is being opened",
                "lock": lock}
    if lock["phase"] == LOCK_PHASE_CLOSING:
        return {"decision": "exit", "reason": "previous version is closing",
                "lock": lock}
    return {"decision": "wait", "reason": "update in progress", "lock": lock}


def remove_stale_update_lock(reason, path=None):
    """Bayat kilidi kaldırır ve güncelleme günlüğüne yazar. Kaldırdıysa True."""
    path = path or update_lock_path()
    try:
        os.remove(path)
        removed = True
    except FileNotFoundError:
        removed = False
    except OSError as exc:
        reason = "%s; could not remove: %s" % (reason, exc)
        removed = False
    try:
        with open(update_log_path(), "a", encoding="utf-8") as f:
            f.write("[launcher %s] stale update lock %s: %s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"),
                "removed" if removed else "not removed", reason))
    except OSError:
        pass
    return removed


# ---------------------------------------------------------------------------
# Kullanıcıya görünen güncelleme metinleri (kalem 5) — TEK KAYNAK.
# Bekleme penceresi (packaging/launcher.py) ve betik bildirimleri buradan
# okur. Dil, /api/update/install isteğiyle gelen arayüz dilidir; bilinmiyorsa
# EN + TR birlikte gösterilir.
# ---------------------------------------------------------------------------

UI_LANGS = ("en", "tr")

UPDATE_TEXTS = {
    "en": {
        "title": "HRMA — update in progress",
        "heading": "Updating HRMA",
        "step.start": "Starting the update",
        "step.waiting_exit": "Waiting for HRMA to close",
        "step.mounting": "Opening the installer image",
        "step.copying": "Copying the new version",
        "step.verifying": "Checking the copied files",
        "step.quarantine_check": "Checking the quarantine attribute",
        "step.quarantine": "Removing the quarantine attribute",
        "step.closing": "Closing the previous version",
        "step.swapping": "Putting the new version in place",
        "step.opening": "Opening the new version",
        "step.restoring": "Restoring the previous version",
        "step.restored": "Opening the previous version",
        "step.done": "Update complete",
        "step.unknown": "Update in progress",
        "progress": "Copied {done} MB of {total} MB",
        "progress_total": "Size to copy: {total} MB",
        "elapsed": "Elapsed: {min} min {sec:02d} s",
        "hint": "This window closes by itself when the update finishes; "
                "HRMA then opens the new version.",
        "log": "Details: {path}",
        "notify.start": "Installing the update. HRMA reopens by itself; if you "
                        "open it meanwhile, it shows the progress and waits.",
        "notify.start.sub": "Update in progress",
        "notify.fail": "Automatic update could not finish. The installer has "
                       "been opened - please install it manually.",
        "notify.fail.sub": "Update",
        "notify.done": "HRMA has been updated and is opening now.",
        "notify.done.sub": "Update complete",
        "notify.wait": "HRMA is being updated; it opens by itself when the "
                       "update finishes.",
        # Güncelleme penceresi (V307/GÜNCELLEME-EKRAN; hrma/utils/update_window.py)
        "step.installing": "Installing the new version",
        "step.checking_install": "Checking the installation",
        "window.heading": "Updating HRMA — please wait",
        "window.title.ok": "HRMA — update complete",
        "window.title.failed": "HRMA — update not completed",
        "window.heading.ok": "Update complete",
        "window.heading.failed": "The update could not be completed",
        "window.versions": "{from} → {to}",
        "window.version_to": "New version: {to}",
        "window.hint": "This window closes by itself when the update finishes "
                       "and HRMA opens the new version. Closing this window "
                       "does not stop the update.",
        "window.ok": "The new version of HRMA is opening. This window closes "
                     "in a few seconds.",
        "window.long": "The update is taking longer than usual (more than "
                       "{min} minutes). The details file shows the last step.",
        "window.close": "Close",
        "window.installer": "Installer: {path}",
        "window.reason.app_not_closed": "HRMA did not close within "
                                        "{exit_wait} seconds.",
        "window.reason.mktemp_failed": "A temporary folder for the installer "
                                       "image could not be created.",
        "window.reason.mount_failed": "The installer image could not be "
                                      "opened.",
        "window.reason.no_app_in_dmg": "No HRMA application was found in the "
                                       "installer image.",
        "window.reason.copy_failed": "The new version could not be copied.",
        "window.reason.staged_incomplete": "The copied new version is "
                                           "incomplete.",
        "window.reason.instance_running": "Another HRMA window did not close, "
                                          "so the new version was not put in "
                                          "place.",
        "window.reason.swap_failed": "The new version could not be put in "
                                     "place.",
        "window.reason.new_version_not_started": "The new version did not "
                                                 "start within {verify} "
                                                 "seconds.",
        "window.reason.interrupted": "The update helper was stopped.",
        "window.reason.unexpected": "The update ended unexpectedly.",
        "window.reason.helper_gone": "The update helper closed without "
                                     "reporting a result.",
        "window.reason.silent_install_failed": "The silent installation did "
                                               "not finish.",
        "window.action.mac_opened": "The installer has been opened: drag HRMA "
                                    "to the Applications folder to install it "
                                    "manually. The previous version is still "
                                    "in place.",
        "window.action.redownload": "Download the installer again: open HRMA "
                                    "and start the update again. The previous "
                                    "version is still in place.",
        "window.action.mac_restored": "The previous version has been restored "
                                      "and is opening. The installer has also "
                                      "been opened if you want to install it "
                                      "manually.",
        "window.action.manual": "Open HRMA again. If it does not open or is "
                                "not updated, open the installer below and "
                                "install it manually.",
        "window.action.win_opened": "The regular installer has been started: "
                                    "follow its steps to finish the "
                                    "installation.",
    },
    "tr": {
        "title": "HRMA — güncelleme sürüyor",
        "heading": "HRMA güncelleniyor",
        "step.start": "Güncelleme başlıyor",
        "step.waiting_exit": "HRMA'nın kapanması bekleniyor",
        "step.mounting": "Kurulum görüntüsü açılıyor",
        "step.copying": "Yeni sürüm kopyalanıyor",
        "step.verifying": "Kopyalanan dosyalar denetleniyor",
        "step.quarantine_check": "Karantina özniteliği denetleniyor",
        "step.quarantine": "Karantina kaldırılıyor",
        "step.closing": "Önceki sürüm kapatılıyor",
        "step.swapping": "Yeni sürüm yerine konuyor",
        "step.opening": "Yeni sürüm açılıyor",
        "step.restoring": "Önceki sürüm geri yükleniyor",
        "step.restored": "Önceki sürüm açılıyor",
        "step.done": "Güncelleme tamamlandı",
        "step.unknown": "Güncelleme sürüyor",
        "progress": "Kopyalanan: {done} MB / {total} MB",
        "progress_total": "Kopyalanacak boyut: {total} MB",
        "elapsed": "Geçen süre: {min} dk {sec:02d} sn",
        "hint": "Güncelleme bitince bu pencere kendiliğinden kapanır ve HRMA "
                "yeni sürümüyle açılır.",
        "log": "Ayrıntılar: {path}",
        "notify.start": "Güncelleme kuruluyor. HRMA kendiliğinden yeniden "
                        "açılacak; bu sırada açarsanız ilerlemeyi gösterip bekler.",
        "notify.start.sub": "Güncelleme sürüyor",
        "notify.fail": "Otomatik güncelleme tamamlanamadı. Kurulum dosyası "
                       "açıldı; lütfen elle kurun.",
        "notify.fail.sub": "Güncelleme",
        "notify.done": "HRMA güncellendi ve şimdi açılıyor.",
        "notify.done.sub": "Güncelleme tamamlandı",
        "notify.wait": "HRMA güncelleniyor; güncelleme bitince kendiliğinden "
                       "açılacak.",
        # Güncelleme penceresi (V307/GÜNCELLEME-EKRAN; hrma/utils/update_window.py)
        "step.installing": "Yeni sürüm kuruluyor",
        "step.checking_install": "Kurulum denetleniyor",
        "window.heading": "HRMA güncelleniyor — lütfen bekleyin",
        "window.title.ok": "HRMA — güncelleme tamamlandı",
        "window.title.failed": "HRMA — güncelleme tamamlanamadı",
        "window.heading.ok": "Güncelleme tamamlandı",
        "window.heading.failed": "Güncelleme tamamlanamadı",
        "window.versions": "{from} → {to}",
        "window.version_to": "Yeni sürüm: {to}",
        "window.hint": "Güncelleme bitince bu pencere kendiliğinden kapanır ve "
                       "HRMA yeni sürümüyle açılır. Bu pencereyi kapatmak "
                       "güncellemeyi durdurmaz.",
        "window.ok": "HRMA'nın yeni sürümü açılıyor. Bu pencere birkaç saniye "
                     "içinde kapanır.",
        "window.long": "Güncelleme olağandan uzun sürüyor ({min} dakikayı "
                       "geçti). Son adım ayrıntılar dosyasında görünür.",
        "window.close": "Kapat",
        "window.installer": "Kurulum dosyası: {path}",
        "window.reason.app_not_closed": "HRMA {exit_wait} saniye içinde "
                                        "kapanmadı.",
        "window.reason.mktemp_failed": "Kurulum görüntüsü için geçici klasör "
                                       "oluşturulamadı.",
        "window.reason.mount_failed": "Kurulum görüntüsü açılamadı.",
        "window.reason.no_app_in_dmg": "Kurulum görüntüsünde HRMA uygulaması "
                                       "bulunamadı.",
        "window.reason.copy_failed": "Yeni sürüm kopyalanamadı.",
        "window.reason.staged_incomplete": "Kopyalanan yeni sürüm eksik.",
        "window.reason.instance_running": "Açık kalan başka bir HRMA penceresi "
                                          "kapanmadığı için yeni sürüm yerine "
                                          "konmadı.",
        "window.reason.swap_failed": "Yeni sürüm yerine konamadı.",
        "window.reason.new_version_not_started": "Yeni sürüm {verify} saniye "
                                                 "içinde açılmadı.",
        "window.reason.interrupted": "Güncelleme yardımcısı durduruldu.",
        "window.reason.unexpected": "Güncelleme beklenmedik biçimde sona "
                                    "erdi.",
        "window.reason.helper_gone": "Güncelleme yardımcısı sonuç "
                                     "bildirmeden kapandı.",
        "window.reason.silent_install_failed": "Sessiz kurulum tamamlanamadı.",
        "window.action.mac_opened": "Kurulum dosyası açıldı: HRMA'yı "
                                    "Uygulamalar klasörüne sürükleyerek elle "
                                    "kurabilirsiniz. Önceki sürüm yerinde "
                                    "duruyor.",
        "window.action.redownload": "Kurulum dosyasını yeniden indirin: "
                                    "HRMA'yı açıp güncellemeyi yeniden "
                                    "başlatın. Önceki sürüm yerinde duruyor.",
        "window.action.mac_restored": "Önceki sürüm geri yüklendi ve açılıyor. "
                                      "Elle kurmak isterseniz kurulum dosyası "
                                      "da açıldı.",
        "window.action.manual": "HRMA'yı yeniden açın. Açılmazsa ya da "
                                "güncellenmemişse aşağıdaki kurulum dosyasını "
                                "açıp elle kurun.",
        "window.action.win_opened": "Normal kurulum programı başlatıldı: "
                                    "adımlarını izleyerek kurulumu tamamlayın.",
    },
}


def normalize_ui_lang(value):
    """Arayüz dili: yalnız 'en' / 'tr'; başka her şey None (EN + TR birlikte)."""
    return value if isinstance(value, str) and value in UI_LANGS else None


# /api/update/install isteğiyle gelen arayüz dili (hrma/app.py update_install
# yazar, launch_helper okur). Kurulum isteği uygulama başına tek seferliktir;
# dil gelmezse None kalır → bildirim ve pencere EN + TR birlikte.
_ui_lang = None


def set_ui_language(value):
    """Kurulum isteğindeki arayüz dilini kaydeder; kaydedilen değeri döndürür."""
    global _ui_lang
    _ui_lang = normalize_ui_lang(value)
    return _ui_lang


def helper_messages(lang):
    """Betik bildirim metinleri: dil biliniyorsa o dilde, değilse EN + TR."""
    lang = normalize_ui_lang(lang)
    out = {}
    for anahtar, ad in (("notify.start", "MSG_START"),
                        ("notify.start.sub", "SUB_START"),
                        ("notify.fail", "MSG_FAIL"),
                        ("notify.fail.sub", "SUB_FAIL"),
                        ("notify.done", "MSG_DONE"),
                        ("notify.done.sub", "SUB_DONE")):
        if lang:
            out[ad] = UPDATE_TEXTS[lang][anahtar]
        else:
            ayrac = " / " if anahtar.endswith(".sub") else "\n"
            out[ad] = UPDATE_TEXTS["en"][anahtar] + ayrac + UPDATE_TEXTS["tr"][anahtar]
    return out


def _mb_text(kb, lang):
    """KB → tam MB, dilin binlik ayırıcısıyla (TR '1.348', EN '1,348')."""
    s = "{:,}".format(int(round(kb / 1024.0)))
    return s.replace(",", ".") if lang == "tr" else s


def _one_lang_view(lock, lang, now):
    t = UPDATE_TEXTS[lang]
    lock = lock or {}
    step = lock.get("step")
    v = {
        "title": t["title"],
        "heading": t["heading"],
        "step": t.get("step.%s" % step, t["step.unknown"]),
        "progress": "",
        "elapsed": "",
        "hint": t["hint"],
        "log": t["log"].format(
            path=update_log_path().replace(os.path.expanduser("~"), "~", 1)),
        "notify_wait": t["notify.wait"],
    }
    done, total = lock.get("done_kb"), lock.get("total_kb")
    if step == "copying" and total:
        if done is not None:
            v["progress"] = t["progress"].format(
                done=_mb_text(done, lang), total=_mb_text(total, lang))
        else:
            v["progress"] = t["progress_total"].format(
                total=_mb_text(total, lang))
    started = lock.get("started")
    if started is not None and now >= started:
        sn = int(now - started)
        v["elapsed"] = t["elapsed"].format(min=sn // 60, sec=sn % 60)
    return v


def update_waiting_view(lock, now=None):
    """Bekleme penceresinin içeriği — yalnız kilitteki GERÇEK veriden.

    ``fraction`` yalnız adım "copying" iken ve betiğin ``du`` ile ölçtüğü
    kopyalanan ve toplam boyut varsa (ve kopyalanan ≤ toplam) verilir; yoksa
    None: ölçülemeyen adım yalnız adıyla görünür. Zamana bağlı ilerleme YOK.
    """
    now = time.time() if now is None else now
    lock = lock or {}
    lang = normalize_ui_lang(lock.get("lang"))
    if lang:
        v = _one_lang_view(lock, lang, now)
    else:
        en = _one_lang_view(lock, "en", now)
        tr = _one_lang_view(lock, "tr", now)
        v = {k: ("%s\n%s" % (en[k], tr[k]) if en[k] else en[k]) for k in en}
        v["title"] = "%s / %s" % (en["title"], tr["title"])
    v["lang"] = lang
    done, total = lock.get("done_kb"), lock.get("total_kb")
    v["fraction"] = (done / float(total)
                     if lock.get("step") == "copying" and total
                     and done is not None and 0 <= done <= total else None)
    return v


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
# sorunlarını kökten keser). Sıra: PID DMG HEDEF LOG [KİLİT].
# Akış: kilit → bekle → bağla → staging'e kopyala → doğrula → takas → yeni
# sürüm GERÇEKTEN AÇILANA KADAR eskiyi tut → açılmazsa geri yükle → kilidi
# kaldır (her çıkış yolunda, trap EXIT).
#
# ŞABLONDUR: ``# @@AYARLAR@@`` satırını :func:`build_mac_helper` sabitlerle
# değiştirir; betik her zaman build_mac_helper ile üretilir.
MAC_HELPER = r"""#!/bin/bash
# HRMA otomatik guncelleme yardimcisi - update_checker tarafindan uretilir.
PID="$1"; DMG="$2"; TARGET="$3"; LOG="$4"; LOCK="${5:-}"
# Pencere betigi ve durum dosyasi bu betigin YANINDA (self_install.py
# _helper_dir); yol argumani eklenmez, cagri sozlesmesi degismez.
SELF_DIR=""
case "$0" in /*/*) SELF_DIR="${0%/*}" ;; esac
cd /
exec >>"$LOG" 2>&1
echo "=== HRMA update helper started: $(date) ==="
echo "pid=$PID dmg=$DMG target=$TARGET lock=$LOCK"

# @@AYARLAR@@

MNT=""; MNT_DIR=""; STAGING=""; OLD=""; DITTO_PID=""
STEP="start"; PHASE="wait"; DONE_KB=""; TOTAL_KB=""
RESULT="running"; ERR_CODE=""; WIN_PID=""
STATUS=""; WIN_JS=""
if [ -n "$SELF_DIR" ]; then
    STATUS="$SELF_DIR/$STATUS_NAME"
    WIN_JS="$SELF_DIR/$WINDOW_NAME"
fi
T_START="$(date +%s)"
echo "versions: ${FROM_VERSION:-?} -> ${TO_VERSION:-?}"

# Guncelleme kilidi (hrma/utils/self_install.py UPDATE_LOCK_*): acilis bunu
# okur; gecerliyse eski surumu acmaz. Atomik yazim: gecici dosya + mv.
# target= satiri EN SONDA (yol satir sonu icerse bile dosya sonuna dek okunur).
write_lock() {
    [ -n "$LOCK" ] || return 0
    local tmp="$LOCK.tmp.$$"
    if { printf '%s\n' "$LOCK_HEADER"
         printf 'pid=%s\nstarted=%s\nstep=%s\nphase=%s\n' "$$" "$T_START" "$STEP" "$PHASE"
         printf 'done_kb=%s\ntotal_kb=%s\nlang=%s\n' "$DONE_KB" "$TOTAL_KB" "$UI_LANG"
         printf 'target=%s\n' "$TARGET"; } >"$tmp" 2>/dev/null \
       && mv -f "$tmp" "$LOCK" 2>/dev/null; then
        return 0
    fi
    rm -f "$tmp" 2>/dev/null
    echo "WARNING: could not write the update lock: $LOCK"
    return 0
}

# Durum dosyasi (self_install.py UPDATE_STATUS_*): guncelleme penceresi
# YALNIZ bunu okur. Atomik yazim (gecici dosya + mv); son satir end=1.
# Yol icermez; adim/oran yalniz betigin gercekten bildigi degerdir.
write_status() {
    [ -n "$STATUS" ] || return 0
    local tmp="$STATUS.tmp.$$"
    if { printf '%s\n' "$STATUS_HEADER"
         printf 'pid=%s\nstarted=%s\nstep=%s\nphase=%s\n' "$$" "$T_START" "$STEP" "$PHASE"
         printf 'done_kb=%s\ntotal_kb=%s\nlang=%s\n' "$DONE_KB" "$TOTAL_KB" "$UI_LANG"
         printf 'from_version=%s\nto_version=%s\n' "$FROM_VERSION" "$TO_VERSION"
         printf 'result=%s\nerror=%s\nend=1\n' "$RESULT" "$ERR_CODE"; } >"$tmp" 2>/dev/null \
       && mv -f "$tmp" "$STATUS" 2>/dev/null; then
        return 0
    fi
    rm -f "$tmp" 2>/dev/null
    echo "WARNING: could not write the update status: $STATUS"
    return 0
}

# Kilit (acilis okur) + durum (pencere okur) birlikte guncellenir.
publish() { write_lock; write_status; }

# Adim degisimi: gunluge zamanla yazilir, kilide ve durum dosyasina islenir.
set_step() {
    STEP="$1"; PHASE="$2"; DONE_KB=""; TOTAL_KB=""
    echo "step: $STEP phase=$PHASE t+$(( $(date +%s) - T_START ))s ($(date +%T))"
    publish
}

# Guncelleme penceresi (V307/GUNCELLEME-EKRAN): uygulama paketinden BAGIMSIZ
# surec - sistemin osascript'i (JXA + AppKit); paket ici Python'a baglanmaz.
# Pencere betigi yoksa ya da baslatilamazsa guncelleme yine surer; o durumda
# bildirimler (notify) eskisi gibi gider. Yollar arguman olarak gecer.
window_alive() { [ -n "$WIN_PID" ] && kill -0 "$WIN_PID" 2>/dev/null; }
start_window() {
    [ -n "$STATUS" ] && [ -f "$WIN_JS" ] || { echo "update window: not available"; return 0; }
    osascript -l JavaScript "$WIN_JS" "$STATUS" "$$" "$LOG" "$DMG" </dev/null >/dev/null &
    WIN_PID=$!
    echo "update window started: pid=$WIN_PID"
}

# HER cikis yolunda (basari, fallback, geri yukleme, TERM/INT/HUP): yarim
# takas guvencesi, staging/baglama temizligi, kilidin kaldirilmasi.
on_exit() {
    local rc=$?
    if [ -n "$DITTO_PID" ]; then kill "$DITTO_PID" 2>/dev/null; wait "$DITTO_PID" 2>/dev/null; fi
    if [ -n "$OLD" ] && [ ! -e "$TARGET" ] && [ -d "$OLD" ]; then
        mv "$OLD" "$TARGET" && echo "exit guard: previous version put back in place"
    fi
    if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then rm -rf "$STAGING"; fi
    if [ -n "$MNT" ]; then hdiutil detach "$MNT" -force >/dev/null 2>&1; fi
    if [ -n "$MNT_DIR" ]; then rmdir "$MNT_DIR" 2>/dev/null; fi
    # Sonucu yazilmamis cikis (sinyal / beklenmedik hata): pencere nedenini
    # gostersin. Durum, yarim takas guvencesinden SONRA yazilir.
    if [ "$RESULT" = "running" ]; then
        RESULT="failed"
        case "$rc" in
            129|130|143) ERR_CODE="interrupted" ;;
            *) [ -n "$ERR_CODE" ] || ERR_CODE="unexpected" ;;
        esac
    fi
    write_status
    if [ -n "$LOCK" ]; then rm -f "$LOCK" "$LOCK.tmp.$$" 2>/dev/null && echo "update lock removed"; fi
    echo "=== HRMA update helper exit rc=$rc t+$(( $(date +%s) - T_START ))s: $(date) ==="
}
trap on_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP

# Kullaniciya gorunur geri bildirim (2026-07-24 saha hatasi): uygulama
# kapandiktan sonra kopyalama birkac dakika suruyor ve macOS'ta ekranda
# hicbir sey olmuyordu; kullanici guncellemenin coktugunu sanip eski
# surumu elle aciyordu. Windows yardimcisinin konsol penceresinin karsiligi
# olarak burada sistem bildirimi kullanilir.
# Metin AppleScript kaynagina GOMULMEZ, arguman olarak gider (tirnak ve
# Turkce karakter guvenli). Metinler kullanicinin arayuz dilinde (MSG_*,
# build_mac_helper; dil bilinmiyorsa EN + TR birlikte).
# Guncelleme penceresi aciksa bildirim GITMEZ (ayni bilgi pencerede).
notify() {
    if window_alive; then return 0; fi
    osascript -e 'on run argv' \
        -e 'display notification (item 1 of argv) with title "HRMA" subtitle (item 2 of argv)' \
        -e 'end run' "$1" "$2" >/dev/null 2>&1 || true
}

# fallback NEDEN KOD: kod pencerenin hata metnini secer
# (self_install.py UPDATE_ERROR_ACTIONS).
fallback() {
    echo "FALLBACK: $1 - opening the DMG for manual installation"
    [ "$RESULT" = "running" ] && RESULT="failed"
    [ -n "$ERR_CODE" ] || ERR_CODE="${2:-unexpected}"
    if [ -n "$MNT" ]; then hdiutil detach "$MNT" -force >/dev/null 2>&1; MNT=""; fi
    write_status
    notify "$MSG_FAIL" "$SUB_FAIL"
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

# Hedef paketten calisan surecler (yalniz bu kullanici, bu betik haric).
# Gercek HRMA sureci: $TARGET/Contents/MacOS/HRMA -> hrma_baslat.sh ->
# $TARGET/Contents/Resources/python/bin/python3.12 .../launcher.py (ayni PID).
UID_SELF="$(id -u)"
bundle_pids() {
    ps -x -U "$UID_SELF" -o pid= -o command= 2>/dev/null | while read -r p c; do
        [ "$p" = "$$" ] && continue
        case "$c" in
            *"$TARGET/Contents/"*) echo "$p" ;;
        esac
    done
}

# Hedef paketten calisan surecleri kapat: once kendiliginden kapanmalari
# beklenir (bekleme penceresi "closing" asamasini gorup kapanir), sonra
# SIGTERM. Hala calisan varsa 1 doner (takas YAPILMAZ).
close_bundle_processes() {
    local pids deadline p
    deadline=$(( $(date +%s) + CLOSE_WAIT_S ))
    pids="$(bundle_pids)"
    while [ -n "$pids" ] && [ "$(date +%s)" -lt "$deadline" ]; do
        sleep 0.5
        pids="$(bundle_pids)"
    done
    [ -z "$pids" ] && return 0
    pids="$(echo $pids)"
    echo "HRMA still running from the target after ${CLOSE_WAIT_S}s: $pids - sending SIGTERM"
    for p in $pids; do echo "  $p: $(ps -p "$p" -o command= 2>/dev/null | cut -c1-200)"; done
    kill -TERM $pids 2>/dev/null
    deadline=$(( $(date +%s) + TERM_WAIT_S ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        sleep 0.5
        if [ -z "$(bundle_pids)" ]; then echo "closed after SIGTERM"; return 0; fi
    done
    echo "still running after SIGTERM: $(echo $(bundle_pids))"
    return 1
}

# ps etime ([[gg-]ss:]dd:ss) -> saniye
etime_s() {
    local t="$1" d=0 h=0 m=0 s=0 a b c
    case "$t" in *-*) d="${t%%-*}"; t="${t#*-}" ;; esac
    IFS=: read -r a b c <<< "$t"
    if [ -n "$c" ]; then h="$a"; m="$b"; s="$c"; else m="$a"; s="$b"; fi
    echo $(( 10#${d:-0} * 86400 + 10#${h:-0} * 3600 + 10#${m:-0} * 60 + 10#${s:-0} ))
}

# 'open' SONRASI hedef paketten baslamis YENI surec: BEFORE listesinde yok
# ve yasi 'open'dan bu yana gecen sureden buyuk degil.
new_bundle_pid() {
    local p et
    for p in $(bundle_pids); do
        case "$BEFORE" in *" $p "*) continue ;; esac
        et="$(ps -p "$p" -o etime= 2>/dev/null | tr -d ' ')"
        [ -n "$et" ] || continue
        [ "$(etime_s "$et")" -le $(( $(date +%s) - OPEN_T + 1 )) ] || continue
        echo "$p"
        return 0
    done
    return 1
}

set_step "waiting_exit" "$PHASE_WAIT"
start_window

# 1) Uygulamanin kapanmasini bekle (en cok EXIT_WAIT_S sn). PID yeniden kullanima
#    karsi komut satiri da dogrulanir: bizim bundle degilse olmus sayilir.
for _ in $(seq 1 "$EXIT_WAIT_S"); do
    CMD="$(ps -p "$PID" -o command= 2>/dev/null)"
    [ -z "$CMD" ] && break
    case "$CMD" in
        *"$TARGET"*) sleep 1 ;;
        *) break ;;
    esac
done
CMD="$(ps -p "$PID" -o command= 2>/dev/null)"
case "$CMD" in
    *"$TARGET"*) fallback "application did not exit in time" app_not_closed ;;
esac
sleep 1  # dosya tanitici birakma payi

# 2) DMG'yi baglan (baglama noktasi kullanicinin gecici dizininde)
notify "$MSG_START" "$SUB_START"
set_step "mounting" "$PHASE_WAIT"
TMPBASE="${TMPDIR:-/tmp}"; TMPBASE="${TMPBASE%/}"
MNT_DIR="$(mktemp -d "$TMPBASE/hrma-update-XXXXXX")" || { MNT_DIR=""; fallback "mktemp failed" mktemp_failed; }
MNT="$MNT_DIR"
hdiutil attach -nobrowse -noverify -noautoopen -readonly \
    -mountpoint "$MNT" "$DMG" || fallback "hdiutil attach failed" mount_failed
echo "mounted: $MNT ($(date +%T))"

SRC=""
for cand in "$MNT"/*.app; do
    [ -d "$cand" ] && SRC="$cand" && break
done
[ -z "$SRC" ] && fallback "no .app found inside the dmg" no_app_in_dmg

# 3) Hedefin YANINA kopyala (ayni disk bolumu -> mv = anlik adlandirma)
PARENT="$(dirname "$TARGET")"
BASE="$(basename "$TARGET")"
STAGING="$PARENT/.$BASE.update.$$"
OLD="$PARENT/.$BASE.old.$$"
rm -rf "$STAGING"
set_step "copying" "$PHASE_WAIT"
# Gercek ilerleme: toplam = kaynagin du olcumu, kopyalanan = staging'in du
# olcumu (PROGRESS_INTERVAL_S aralikla). Zamana bagli/uydurma deger YAZILMAZ;
# olculemezse alan bos kalir ve pencere yalniz adimin adini gosterir.
T="$(du -sk "$SRC" 2>/dev/null | awk '{print $1}')"
case "$T" in ''|*[!0-9]*) T="" ;; esac
TOTAL_KB="$T"
publish
echo "copying ($(date +%T)), source ${TOTAL_KB:-?} KB..."
# --noqtn: kopya karantina ozniteligi TASIMAZ (eski akistaki ~11-14 sn'lik
# xattr -dr adimi kalkar; olcum: docs/scofield/raw/OH/V306/guncelleme/
# olcum_kalem3.json - karantinali DMG'den ditto varsayilani kopyaya
# "0083;00000000;;" tasiyor, --noqtn tasimiyor).
ditto --noqtn "$SRC" "$STAGING" &
DITTO_PID=$!
# Kisa aralikla (0,5 sn) kopyanin bitip bitmedigine bakilir (bitis
# gecikmesiz gorulur); du olcumu yalniz PROGRESS_INTERVAL_S'de bir.
LAST_DU="$(date +%s)"
while kill -0 "$DITTO_PID" 2>/dev/null; do
    sleep 0.5
    kill -0 "$DITTO_PID" 2>/dev/null || break
    [ $(( $(date +%s) - LAST_DU )) -ge "$PROGRESS_INTERVAL_S" ] || continue
    LAST_DU="$(date +%s)"
    D="$(du -sk "$STAGING" 2>/dev/null | awk '{print $1}')"
    case "$D" in ''|*[!0-9]*) continue ;; esac
    DONE_KB="$D"
    echo "progress: copied ${DONE_KB} KB of ${TOTAL_KB:-?} KB"
    publish
done
wait "$DITTO_PID"; DITTO_RC=$?
DITTO_PID=""
if [ "$DITTO_RC" -ne 0 ]; then
    rm -rf "$STAGING"
    fallback "copy (ditto) failed (rc=$DITTO_RC)" copy_failed
fi
D="$(du -sk "$STAGING" 2>/dev/null | awk '{print $1}')"
echo "copied ($(date +%T)): ${D:-?} KB (source ${TOTAL_KB:-?} KB)"
set_step "verifying" "$PHASE_WAIT"
detach_dmg

# 3b) Staging butunlugu: yarim kopyayla takas YAPILMAZ
if [ ! -d "$STAGING/Contents/MacOS" ] || \
   [ ! -d "$STAGING/Contents/Resources/app/hrma" ]; then
    rm -rf "$STAGING"
    fallback "staged copy is incomplete" staged_incomplete
fi

# 3c) Karantina savunmasi (takastan ONCE, staging uzerinde): kopya --noqtn
#     ile yapildi; yine de kalmis mi salt okuma taramasiyla denetlenir
#     (62 595 dosyada ~1,5 sn). Kalmissa ya da tarama basarisizsa eski adim
#     uygulanir (xattr -dr) ve gunluge yazilir.
set_step "quarantine_check" "$PHASE_WAIT"
QF="$(find "$STAGING" -xattrname com.apple.quarantine -print -quit 2>/dev/null)"; QRC=$?
if [ "$QRC" -ne 0 ] || [ -n "$QF" ]; then
    if [ -n "$QF" ]; then
        echo "quarantine check: found on $QF - removing it recursively"
    else
        echo "quarantine check: scan failed (rc=$QRC) - removing it recursively"
    fi
    set_step "quarantine" "$PHASE_WAIT"
    xattr -dr com.apple.quarantine "$STAGING" 2>/dev/null
    echo "quarantine removed ($(date +%T))"
else
    echo "quarantine check: clean ($(date +%T))"
fi

# 4) Eski surum kapatilir (V306 kalem 4). Hedef paketten calisan surec
#    varken takas YAPILMAZ: 'open' yeni surumu baslatmak yerine calisani
#    one getirir ve acilis dogrulamasi onu "yeni surum" sanar. Bekleme
#    pencereleri "closing" asamasini gorup kendiliginden kapanir.
set_step "closing" "$PHASE_CLOSING"
if ! close_bundle_processes; then
    rm -rf "$STAGING"
    fallback "another HRMA instance from the target is still running" instance_running
fi

# 5) Anlik degisim: eskiyi kenara al, yeniyi oturt; olmazsa geri al
set_step "swapping" "$PHASE_CLOSING"
if ! mv "$TARGET" "$OLD"; then
    rm -rf "$STAGING"
    fallback "could not move the old application aside" swap_failed
fi
if ! mv "$STAGING" "$TARGET"; then
    mv "$OLD" "$TARGET"
    rm -rf "$STAGING"
    fallback "could not move the new application into place" swap_failed
fi

# 6) Yeniden baslat ve yeni surum GERCEKTEN acildi mi dogrula (V306 kalem 4).
#    Kanit: hedef paketten calisan, 'open' ONCESI listede OLMAYAN, 'open'dan
#    SONRA baslamis ve LAUNCH_STABLE_S boyunca yasayan surec. Eski denetim
#    (ps | grep -F "$TARGET/") guncelleme sirasinda acilmis ESKI sureci de
#    sayiyor, basari deyip calisan eski paketi siliyordu. Karantina 3c'de,
#    takastan once ele alindi.
BEFORE=" $(echo $(bundle_pids)) "
set_step "opening" "$PHASE_LAUNCH"
OPEN_T="$(date +%s)"
open "$TARGET"
NEW_PID=""; REOPENED=""
while [ $(( $(date +%s) - OPEN_T )) -lt "$LAUNCH_VERIFY_S" ]; do
    sleep 1
    CAND="$(new_bundle_pid)"
    if [ -n "$CAND" ]; then
        sleep "$LAUNCH_STABLE_S"
        if kill -0 "$CAND" 2>/dev/null; then NEW_PID="$CAND"; break; fi
        echo "new process $CAND exited within ${LAUNCH_STABLE_S}s"
    fi
    if [ -z "$REOPENED" ] && [ $(( $(date +%s) - OPEN_T )) -ge "$REOPEN_AFTER_S" ]; then
        echo "no new HRMA process ${REOPEN_AFTER_S}s after open - asking LaunchServices once more"
        open "$TARGET"
        REOPENED=1
    fi
done
if [ -z "$NEW_PID" ]; then
    echo "new version did not start - restoring the previous version"
    set_step "restoring" "$PHASE_CLOSING"
    close_bundle_processes
    rm -rf "$TARGET"
    mv "$OLD" "$TARGET"
    RESULT="restored"; ERR_CODE="new_version_not_started"
    set_step "restored" "$PHASE_LAUNCH"
    open "$TARGET"
    fallback "update failed, previous version restored" new_version_not_started
fi
echo "new version running: pid=$NEW_PID ($(ps -p "$NEW_PID" -o command= 2>/dev/null | cut -c1-200))"
# Sonuc, yeni surum DOGRULANDIKTAN sonra yazilir; pencere "tamamlandi" der ve
# kendiliginden kapanir. Eski kopyanin silinmesi (birkac sn) bunu bekletmez.
RESULT="ok"
set_step "done" "$PHASE_LAUNCH"
notify "$MSG_DONE" "$SUB_DONE"
rm -rf "$OLD"
echo "=== HRMA update complete: $(date) ==="
"""


def _bash_quote(value):
    """Bash ANSI-C dizgesi ($'...'): betik ASCII kalır, değer bayt bayt doğru.

    Yazdırılabilir ASCII (tek tırnak ve ters bölü hariç) olduğu gibi, geri
    kalan her bayt (Türkçe harflerin UTF-8 baytları dahil) ``\\xHH`` olarak
    yazılır. Komut ikamesi/genişletme $'...' içinde ÇALIŞMAZ.
    """
    out = []
    for b in str(value).encode("utf-8"):
        c = chr(b)
        if 0x20 <= b < 0x7f and c not in "'\\":
            out.append(c)
        else:
            out.append("\\x%02x" % b)
    return "$'" + "".join(out) + "'"


def build_mac_helper(lang=None, from_version=None, to_version=None,
                     **sure_ayari):
    """Çalıştırılacak macOS yardımcı betiği (şablon + sabitler).

    Sabitler bu modülün TEK KAYNAK blokundan gömülür; betik ASCII'dir.
    ``from_version`` / ``to_version`` güncelleme penceresinde gösterilir;
    :func:`safe_version` biçimine uymayan değer boş yazılır (pencere sürüm
    satırını gizler). ``sure_ayari`` yalnız testler içindir (ör.
    ``progress_interval_s=0.2``): bilinmeyen anahtar hata verir.
    """
    sureler = {"exit_wait_s": HELPER_EXIT_WAIT_S,
               "progress_interval_s": HELPER_PROGRESS_INTERVAL_S,
               "close_wait_s": HELPER_CLOSE_WAIT_S,
               "term_wait_s": HELPER_TERM_WAIT_S,
               "launch_verify_s": HELPER_LAUNCH_VERIFY_S,
               "reopen_after_s": HELPER_REOPEN_AFTER_S,
               "launch_stable_s": HELPER_LAUNCH_STABLE_S}
    bilinmeyen = set(sure_ayari) - set(sureler)
    if bilinmeyen:
        raise TypeError("unknown helper timing: %s" % sorted(bilinmeyen))
    sureler.update(sure_ayari)
    ayarlar = {
        "LOCK_HEADER": UPDATE_LOCK_HEADER,
        "PHASE_WAIT": LOCK_PHASE_WAIT,
        "PHASE_CLOSING": LOCK_PHASE_CLOSING,
        "PHASE_LAUNCH": LOCK_PHASE_LAUNCH,
        "UI_LANG": normalize_ui_lang(lang) or "",
        "STATUS_HEADER": UPDATE_STATUS_HEADER,
        "STATUS_NAME": UPDATE_STATUS_NAME,
        "WINDOW_NAME": UPDATE_WINDOW_MAC_NAME,
        "FROM_VERSION": safe_version(from_version),
        "TO_VERSION": safe_version(to_version),
        "EXIT_WAIT_S": sureler["exit_wait_s"],
        "PROGRESS_INTERVAL_S": sureler["progress_interval_s"],
        "CLOSE_WAIT_S": sureler["close_wait_s"],
        "TERM_WAIT_S": sureler["term_wait_s"],
        "LAUNCH_VERIFY_S": sureler["launch_verify_s"],
        "REOPEN_AFTER_S": sureler["reopen_after_s"],
        "LAUNCH_STABLE_S": sureler["launch_stable_s"],
    }
    ayarlar.update(helper_messages(lang))
    satirlar = ["# Ayarlar: hrma/utils/self_install.py (build_mac_helper)"]
    for ad, deger in ayarlar.items():
        satirlar.append("%s=%s" % (ad, _bash_quote(deger)))
    return MAC_HELPER.replace("# @@AYARLAR@@", "\n".join(satirlar), 1)

# Windows: cmd.exe argüman aktarımı kırılgan olduğundan yollar betiğe
# gömülür; plan_install gömülemeyecek karakterleri zaten elemiştir.
# NSIS kuralları: /S sessiz kurulum; /D= MUTLAK SON parametredir ve
# boşluk içerse bile TIRNAKSIZ yazılır (NSIS satır sonuna kadar okur).
# Kurucu batch icinden dogrudan cagrilir (start KULLANILMAZ — bosluklu
# yollarda baslik/arguman ayristirmasi tuzakli; batch zaten bekler).
# V307/GÜNCELLEME-EKRAN: betik her adımda durum dosyasını
# (UPDATE_STATUS_*, INSTDIR\updater) yazar ve başta güncelleme penceresini
# (PowerShell + WinForms, UPDATE_WINDOW_WIN_NAME) başlatır. Pencere uygulama
# paketine bağlı değildir: sistemin powershell.exe'si (System32) ile koşar;
# NSIS'in süreç kapatma filtresi (ExecutablePath $INSTDIR\*) onu görmez ve
# kurucu updater dizinini silmez. Pencere başlatılamazsa (ör. grup ilkesi
# betikleri yasaklamışsa) bu konsol penceresi eskisi gibi görünür kalır.
# Satır sonu CRLF (build_win_helper): LF'li batch dosyasında 'call :etiket'
# etiket aramasında şaşabilir.
WIN_HELPER = """@echo off
title HRMA Update
cd /d "%TEMP%"
set "HRMA_STATUS={status}"
set "HRMA_STEP=waiting_exit"
set "HRMA_PHASE=wait"
set "HRMA_RESULT=running"
set "HRMA_ERROR="
call :hrma_status
if exist "{window}" start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{window}" -Status "{status}" -Installer "{setup}"
echo.
echo   Updating HRMA to the new version...
echo   HRMA will reopen automatically when the update is complete.
echo   Please do not close this window.
echo.
echo   [1/4] Waiting for HRMA to close
powershell -NoProfile -Command "Wait-Process -Id {pid} -Timeout {exit_wait} -ErrorAction SilentlyContinue" >nul 2>&1
set "HRMA_STEP=installing"
call :hrma_status
echo   [2/4] Installing the new version
"{setup}" /S /D={instdir}
set "HRMA_STEP=checking_install"
call :hrma_status
echo   [3/4] Checking the installation
if not exist "{instdir}\\python\\pythonw.exe" (
  set "HRMA_RESULT=failed"
  set "HRMA_ERROR=silent_install_failed"
  call :hrma_status
  echo   Silent install failed - starting the normal installer instead.
  start "" "{setup}"
  exit /b 1
)
set "HRMA_STEP=opening"
set "HRMA_PHASE=launch"
call :hrma_status
echo   [4/4] Opening the new version
start "" "{instdir}\\python\\pythonw.exe" "{instdir}\\app\\launcher.py"
set "HRMA_STEP=done"
set "HRMA_RESULT=ok"
call :hrma_status
(goto) 2>nul & del "%~f0"
exit /b 0

:hrma_status
(
  echo {header}
  echo pid=
  echo started=
  echo step=%HRMA_STEP%
  echo phase=%HRMA_PHASE%
  echo done_kb=
  echo total_kb=
  echo lang={lang}
  echo from_version={from_version}
  echo to_version={to_version}
  echo result=%HRMA_RESULT%
  echo error=%HRMA_ERROR%
  echo end=1
) 2>nul 1>"%HRMA_STATUS%"
exit /b 0
"""


def _win_updater_path(instdir, name):
    """INSTDIR\\updater\\<ad> (Windows yolu; testler macOS'ta da üretir)."""
    return instdir.rstrip("\\/") + "\\updater\\" + name


def build_win_helper(pid, setup_path, instdir, lang=None, from_version=None,
                     to_version=None):
    """Windows yardımcı betiği (CRLF, ASCII). Yollar ``plan_install``'ın
    ``_CMD_UNSAFE`` kapısından geçmiştir; dil ve sürüm yalnız izinli
    biçimde gömülür (``normalize_ui_lang`` / :func:`safe_version`)."""
    metin = WIN_HELPER.format(
        pid=int(pid), setup=setup_path, instdir=instdir,
        exit_wait=int(HELPER_EXIT_WAIT_S),
        status=_win_updater_path(instdir, UPDATE_STATUS_NAME),
        window=_win_updater_path(instdir, UPDATE_WINDOW_WIN_NAME),
        header=UPDATE_STATUS_HEADER,
        lang=normalize_ui_lang(lang) or "",
        from_version=safe_version(from_version),
        to_version=safe_version(to_version))
    return "\r\n".join(metin.split("\n"))


def _write_helper(plan, content, suffix):
    path = os.path.join(_helper_dir(plan), HELPER_SCRIPT_STEM + suffix)
    # Batch dosyaları cmd.exe'nin yerel kod sayfasıyla okunur; içerik ASCII
    # tutulur (betiklerde Türkçe karakter kullanılmaz).
    with open(path, "w", encoding="ascii", newline="") as f:
        f.write(content)
    return path


def _write_window(plan):
    """Güncelleme penceresi betiğini yardımcı betiğin yanına yazar.

    Pencere bir İYİLEŞTİRMEDİR: yazılamazsa güncelleme yine başlar (betik
    pencere dosyasını bulamayınca bunu günlüğe yazar ve eski bildirimlere
    düşer). Dönüş: yol ya da None; hata fırlatmaz.
    """
    try:
        from hrma.utils import update_window
        if plan["platform"] == "darwin":
            icerik = update_window.build_mac_window()
            ad = UPDATE_WINDOW_MAC_NAME
        else:
            icerik = update_window.build_win_window()
            ad = UPDATE_WINDOW_WIN_NAME
        return _write_helper(plan, icerik, ad[len(HELPER_SCRIPT_STEM):])
    except Exception:
        return None


def launch_helper(plan, installer_path, pid=None, versions=None):
    """Yardımcı betiği (ve güncelleme penceresi betiğini) yazar, betiği
    bağımsız süreç olarak başlatır.

    ``versions``: (kurulu sürüm, kurulacak sürüm) — pencerede gösterilir;
    bilinmeyen/izinsiz biçimli değer gösterilmez.
    Başarıda {"launched": True, "log": ...}; hata fırlatmaz, sorun varsa
    {"launched": False, "error": ...} döner (çağıran manuel moda düşer).
    """
    pid = pid or os.getpid()
    log_path = update_log_path()
    eski, yeni = (tuple(versions) + (None, None))[:2] if versions else (None, None)
    try:
        _write_window(plan)
        if plan["platform"] == "darwin":
            script = _write_helper(
                plan, build_mac_helper(_ui_lang, from_version=eski,
                                       to_version=yeni), ".sh")
            # 5. argüman: güncelleme kilidi (açılış okur, betik her çıkışta
            # kaldırır — bkz. UPDATE_LOCK_* bloğu). Durum dosyası ve pencere
            # betiği betiğin yanındadır (argüman eklenmez).
            subprocess.Popen(
                ["/bin/bash", script, str(pid), installer_path,
                 plan["target"], log_path, update_lock_path()],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, cwd="/",
            )
        else:
            script = _write_helper(
                plan, build_win_helper(pid, installer_path, plan["target"],
                                       lang=_ui_lang, from_version=eski,
                                       to_version=yeni),
                ".bat")
            # Görünür küçük bir konsol: sessiz kurulum 1-2 dk sürer, kullanıcı
            # "uygulama yok oldu" sanmasın. CREATE_NEW_CONSOLE süreci bizim
            # konsolumuzdan da ayırır; uygulama kapanınca yardımcı yaşar.
            # Güncelleme penceresini betik başlatır (WIN_HELPER).
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
