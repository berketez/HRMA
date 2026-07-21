"""Otomatik güncelleme denetleyicisi — GitHub Releases tabanlı.

Uygulama açılışında arayüz /api/update/check'i çağırır; burada GitHub'ın
herkese açık Releases API'sinden en son sürüm etiketi alınır ve yerel
``hrma.__version__`` ile karşılaştırılır. Yeni sürüm varsa arayüz kullanıcıya
"güncelleme var, indirmek ister misiniz?" penceresi gösterir.

Güvenlik notları:
- İndirme adresi İSTEMCİDEN ALINMAZ: sunucu, GitHub API yanıtındaki
  platforma uygun release asset'ini kendisi seçer (URL enjeksiyonu kapalı).
- Ağ hatası/limit aşımı sessizce "güncelleme yok" olarak raporlanır;
  güncelleme kontrolü uygulamanın çalışmasını asla engellemez.
"""

import os
import re
import sys
import json
import time
import threading
import urllib.request

from hrma import __version__

GITHUB_REPO = "berketez/HRMA"
RELEASES_API = "https://api.github.com/repos/%s/releases/latest" % GITHUB_REPO
RELEASES_PAGE = "https://github.com/%s/releases/latest" % GITHUB_REPO

# API yanıtı bu süre boyunca önbellekte tutulur (aynı oturumda her sayfa
# yenilemesinde GitHub'a gitmemek için; anonim limit 60 istek/saat).
CACHE_TTL_S = 6 * 3600
# Ağ hatası sonuçları kısa önbelleklenir: çevrimdışı açılan uygulama ağa
# kavuşunca aynı oturumda güncellemeyi görebilsin (2026-07-14 denetim bulgusu)
ERROR_CACHE_TTL_S = 10 * 60

_cache_lock = threading.Lock()
_cache = {"checked_at": 0.0, "result": None}

# İndirme durumu (tek seferde tek indirme; UI /api/update/status ile izler)
_download_lock = threading.Lock()
_download = {"state": "idle", "pct": 0, "path": "", "error": ""}


def parse_version(text):
    """'v2.3.0', '2.3', 'HRMA-2.3.0-beta' gibi etiketlerden (2, 3, 0) üretir."""
    nums = re.findall(r"\d+", text or "")
    if not nums:
        return (0, 0, 0)
    return tuple(int(n) for n in (nums + ["0", "0"])[:3])


def is_newer(remote_tag, local_version=__version__):
    return parse_version(remote_tag) > parse_version(local_version)


def pick_asset(assets, platform=None):
    """Release asset'lerinden bu platforma uygun kurulum dosyasını seçer.

    macOS → .dmg, Windows → .exe. Uygun asset yoksa None döner (arayüz bu
    durumda tarayıcıda Releases sayfasını açar).
    """
    platform = platform or sys.platform
    if platform == "darwin":
        suffixes = (".dmg",)
    elif platform in ("win32", "cygwin"):
        suffixes = (".exe",)
    else:
        return None
    for asset in assets or []:
        name = (asset.get("name") or "").lower()
        if name.endswith(suffixes):
            return {
                "name": asset.get("name"),
                "url": asset.get("browser_download_url"),
                "size": asset.get("size") or 0,
                # GitHub API asset özeti ("sha256:<hex>") — indirme sonrası
                # bütünlük doğrulaması için (yoksa boyut kontrolüyle yetinilir)
                "digest": asset.get("digest") or "",
            }
    return None


def _fetch_latest_release(timeout_s=8):
    req = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "HRMA-UpdateChecker/" + __version__,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def check_for_update(force=False):
    """Güncelleme durumunu döndürür; sonuç CACHE_TTL_S boyunca önbellekli.

    Dönen sözlük her zaman aynı şemadadır:
    {available, current, latest, notes, page_url, asset, error}
    """
    with _cache_lock:
        onceki = _cache["result"]
        ttl = ERROR_CACHE_TTL_S if (onceki and onceki.get("error")) else CACHE_TTL_S
        fresh = (time.time() - _cache["checked_at"]) < ttl
        if onceki is not None and fresh and not force:
            return onceki

    result = {
        "available": False,
        "current": __version__,
        "latest": None,
        "notes": "",
        "page_url": RELEASES_PAGE,
        "asset": None,
        "error": None,
    }
    try:
        release = _fetch_latest_release()
        tag = release.get("tag_name") or release.get("name") or ""
        result["latest"] = tag
        if is_newer(tag) and not release.get("draft") and not release.get("prerelease"):
            result["available"] = True
            result["notes"] = (release.get("body") or "")[:4000]
            result["page_url"] = release.get("html_url") or RELEASES_PAGE
            result["asset"] = pick_asset(release.get("assets"))
    except Exception as exc:  # ağ yok / limit / 404 (hiç release yok) — sorun değil
        result["error"] = "%s: %s" % (type(exc).__name__, exc)

    with _cache_lock:
        _cache["checked_at"] = time.time()
        _cache["result"] = result
    return result


def _downloads_dir():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def download_status():
    with _download_lock:
        return dict(_download)


def _run_download(url, name, size, digest=""):
    tmp_path = os.path.join(_downloads_dir(), name + ".download")
    final_path = os.path.join(_downloads_dir(), name)
    try:
        import hashlib
        hasher = hashlib.sha256()
        req = urllib.request.Request(
            url, headers={"User-Agent": "HRMA-UpdateChecker/" + __version__}
        )
        with urllib.request.urlopen(req, timeout=30) as resp, \
                open(tmp_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or size or 0)
            done = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                hasher.update(chunk)
                done += len(chunk)
                if total:
                    with _download_lock:
                        _download["pct"] = int(done * 100 / total)
        # Bütünlük: eksik/yarım inmiş ya da bozulmuş dosyayla kurulum
        # denenmesin. Boyut GitHub API'nin bildirdiğiyle, içerik de (API
        # digest verdiyse) SHA-256 özetiyle karşılaştırılır.
        if total and done != total:
            raise IOError("incomplete download: %d of %d bytes" % (done, total))
        if digest.startswith("sha256:"):
            got = hasher.hexdigest()
            if got != digest.split(":", 1)[1].strip().lower():
                raise IOError("sha256 mismatch: downloaded file is corrupted")
        os.replace(tmp_path, final_path)
        with _download_lock:
            _download.update(state="done", pct=100, path=final_path)
        # Kurulum burada BAŞLATILMAZ: arayüz /api/update/install ile sessiz
        # otomatik kurulumu tetikler; otomatik kurulamayan ortamlarda
        # (kaynak kod, yazılamayan hedef) oradan _open_installer'a düşülür.
    except Exception as exc:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        with _download_lock:
            _download.update(state="error", error="%s: %s" % (type(exc).__name__, exc))


def _open_installer(path):
    """İndirilen dmg/exe'yi işletim sistemine açtırır (kurulumu kullanıcı yapar)."""
    try:
        if sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)  # noqa: attribute yalnızca Windows'ta var
    except Exception:
        pass  # açılamazsa dosya yine de Downloads'ta duruyor


def open_download_in_browser():
    """Yedek indirme: asset URL'sini (yoksa Releases sayfasını) sistem
    tarayıcısında açar. Uygulama içi indirme yavaş/başarısız olduğunda
    (GitHub CDN yavaşlığı, ağ kısıtı) veya kullanıcı indirme yöneticisini
    tercih ettiğinde kullanılır. webbrowser.open sunucu tarafında çalıştığı
    için pywebview/exe penceresi, Chromium ve her tarayıcıda aynı davranır.
    """
    info = check_for_update()
    asset = info.get("asset")
    url = (asset or {}).get("url") or info.get("page_url") or RELEASES_PAGE
    try:
        import webbrowser
        webbrowser.open(url)
        return {"opened": True, "url": url}
    except Exception as exc:
        return {"opened": False, "url": url,
                "error": "%s: %s" % (type(exc).__name__, exc)}


def start_install():
    """İndirilen güncellemeyi kurar — mümkünse tam otomatik.

    "auto" modda platforma özgü yardımcı betik bağımsız süreç olarak
    başlatılır ve uygulama kendini kapatır; kurulum ile yeniden açılış
    kullanıcı dokunmadan tamamlanır. Otomatik kurulamayan ortamlarda
    (kaynak koddan çalışma, yazılamayan hedef, betik başlatma hatası)
    "manual" moda düşülür: kurulum dosyası işletim sistemine açtırılır
    (eski davranış). Kurulacak dosya yolu istemciden alınmaz.
    """
    with _download_lock:
        st = dict(_download)
    if st["state"] != "done" or not st["path"] or not os.path.isfile(st["path"]):
        return {"started": False, "reason": "no downloaded installer"}

    from hrma.utils import self_install
    plan = self_install.plan_install(
        st["path"], installer_size=os.path.getsize(st["path"]))
    if plan["mode"] == "auto":
        launched = self_install.launch_helper(plan, st["path"])
        if launched.get("launched"):
            self_install.schedule_app_exit()
            return {"started": True, "mode": "auto", "log": launched.get("log")}
        plan = {"mode": "manual", "reason": launched.get("error", "helper failed")}

    _open_installer(st["path"])
    return {"started": True, "mode": "manual",
            "reason": plan.get("reason"), "path": st["path"]}


def start_download():
    """Platforma uygun asset'i ~/Downloads'a indirmeye başlar (arka planda).

    URL istemciden gelmez: check_for_update() önbelleğindeki GitHub yanıtından
    okunur. Uygun asset yoksa {"started": False, "reason": ...} döner.
    """
    info = check_for_update()
    asset = info.get("asset")
    if not (info.get("available") and asset and asset.get("url")):
        return {"started": False, "reason": "no suitable installer found for this platform",
                "page_url": info.get("page_url")}

    with _download_lock:
        if _download["state"] == "downloading":
            return {"started": True, "already": True}
        _download.update(state="downloading", pct=0, path="", error="")

    threading.Thread(
        target=_run_download,
        args=(asset["url"], asset["name"], asset.get("size") or 0,
              asset.get("digest") or ""),
        daemon=True,
    ).start()
    return {"started": True, "name": asset["name"], "size": asset.get("size") or 0}
