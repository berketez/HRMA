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
import urllib.parse

from hrma import __version__

GITHUB_REPO = "berketez/HRMA"
RELEASES_API = "https://api.github.com/repos/%s/releases/latest" % GITHUB_REPO
RELEASES_PAGE = "https://github.com/%s/releases/latest" % GITHUB_REPO
# API'siz yedek yol (2026-07-24 saha hatası): api.github.com anonim istemciye
# saatte 60 istek verir ve limit IP başınadır — paylaşımlı/NAT arkası bir ağda
# (yurt, ofis, mobil operatör) kullanıcı tek istek bile yapmadan limit dolu
# olabilir, o zaman güncelleme tamamen ölüyordu. Aşağıdaki iki adres normal
# web sayfası yoludur, API kotasına tabi değildir:
#   /releases/latest         → 302 ile /releases/tag/<etiket>'e yönlenir
#   /releases/expanded_assets/<etiket> → asset bağlantılarını içeren parça
RELEASES_ATOM = "https://github.com/%s/releases.atom" % GITHUB_REPO
ASSETS_FRAGMENT = "https://github.com/%s/releases/expanded_assets/%%s" % GITHUB_REPO
# Yedek yoldan gelen indirme adresi yalnız bu önekle kabul edilir (URL enjeksiyonu)
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % GITHUB_REPO

# Sürüm notu gövdesi için üst sınır. DİL BÖLÜMÜ BAŞINA uygulanır, gövdenin
# tamamına değil: v2.6.26'da gövde 16045 karakterdi ve `<!--HRMA-LANG:tr-->`
# imi 8072. karakterde başlıyordu; tek parça [:4000] kırpması Türkçe bölümü
# istemciye HİÇ ulaştırmıyordu, Türkçe arayüzde sürüm notu İngilizce çıkıyordu.
#
# 2026-08-03: sınırın kendisi dayanaksızdı ve 4000 karakter gerçek sürüm
# notlarına yetmiyordu. Ölçüldü: v2.6.26 bölümleri 8161 (en) / 7774 (tr),
# depodaki en büyük tarihsel bölüm 8929 karakter (v2.6.2). Yani her gerçek
# sürüm notu bu sınırın iki katıydı ve kullanıcı notun yarısını cümle
# ortasında kesilmiş hâlde görüyordu — üstelik kesildiğine dair hiçbir işaret
# olmadan. Sınır ölçülen en büyük bölümün ~1,8 katına çekildi; amacı yükü
# sınırlamak, notu budamak değil.
NOTES_MAX_CHARS = 16000
_LANG_MARK_RE = re.compile(r"<!--\s*HRMA-LANG:([a-z]{2})\s*-->", re.I)
# Atom yedek yolunda GitHub HTML yorumlarını düşürür (2026-07-29'da canlı
# akışta ölçüldü: im sayısı 0); orada bölümler sürüm başlıklarından ayrılır.
_SECTION_HEAD_RE = re.compile(r"(?m)^(?=[ \t]*#{0,3}[ \t]*HRMA[ \t]+v?\d)")


def split_notes_by_language(body):
    """Sürüm notu gövdesini dil imlerinden bölüp {'en': ..., 'tr': ...} döndürür."""
    if not body:
        return {}
    bolumler, son_kod, son_son = {}, None, 0
    for m in _LANG_MARK_RE.finditer(body):
        if son_kod is not None:
            bolumler[son_kod] = body[son_son:m.start()].strip()
        son_kod = m.group(1).lower()
        son_son = m.end()
    if son_kod is None:
        return {}
    bolumler[son_kod] = body[son_son:].strip()
    return {k: v for k, v in bolumler.items() if v}


#: Sınır aşıldığında metnin sonuna eklenen beyan. Kırpmanın SESSİZ olmaması
#: şart: kullanıcı yarım kalmış bir cümle görüp onu notun tamamı sanmamalı.
NOTES_CLIP_MARK_EN = "\n\n_… release notes shortened; full text on the release page._"
NOTES_CLIP_MARK_TR = "\n\n_… sürüm notu kısaltıldı; tam metin sürüm sayfasında._"


def _kirp(metin, limit, kod=None):
    """Sınırı aşan metni SATIR SINIRINDA keser ve kesildiğini beyan eder.

    2026-08-03: eskiden düz ``metin[:limit]`` yapılıyordu. Ölçüldü: v2.6.26
    Türkçe bölümü 3989. karakterde, "göndermiyordu" kelimesinin ortasında
    kesiliyor ve kullanıcıya hiçbir işaret verilmiyordu. Yarım cümleyi notun
    tamamı sanmak, ekranın veriden fazlasını söylemesiyle aynı sınıf hata.
    """
    if len(metin) <= limit:
        return metin
    im = NOTES_CLIP_MARK_TR if kod == 'tr' else NOTES_CLIP_MARK_EN
    pay = max(0, limit - len(im))
    kesik = metin[:pay]
    # Satır sınırına geri sar; satır bulunamazsa (tek uzun satır) boşluğa sar.
    for ayrac in ('\n', ' '):
        i = kesik.rfind(ayrac)
        if i > pay * 0.5:          # çok geriye sarıp metni yok etmesin
            kesik = kesik[:i]
            break
    return kesik.rstrip() + im


def clip_notes(body, limit=NOTES_MAX_CHARS):
    """Gövdeyi DİL BÖLÜMÜ BAŞINA kırpar; imleri koruyarak birleştirir."""
    if not body:
        return ""
    bolumler = split_notes_by_language(body)
    if bolumler:
        return "\n\n".join(
            "<!--HRMA-LANG:%s-->\n%s" % (kod, _kirp(metin, limit, kod))
            for kod, metin in bolumler.items()
        )
    parcalar = [x.strip() for x in _SECTION_HEAD_RE.split(body) if x.strip()]
    if len(parcalar) >= 2:
        return "\n\n".join(_kirp(x, limit) for x in parcalar)
    return _kirp(body, limit)

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


def _is_rate_limited(exc):
    """Hatanın GitHub API kota aşımı (403/429) olup olmadığını söyler."""
    code = getattr(exc, "code", None)
    return code in (403, 429)


def _fetch_tag_via_page(timeout_s=8):
    """En son yayın etiketini API'siz alır: /releases/latest 302 ile
    /releases/tag/<etiket>'e yönlenir, yönlendirmenin geldiği adresten
    etiket okunur."""
    req = urllib.request.Request(
        RELEASES_PAGE,
        headers={"User-Agent": "HRMA-UpdateChecker/" + __version__},
        method="HEAD",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        final_url = resp.geturl() or ""
    match = re.search(r"/releases/tag/([^/?#]+)", final_url)
    if not match:
        raise IOError("could not resolve latest tag from %r" % final_url)
    return urllib.parse.unquote(match.group(1))


def parse_asset_links(html):
    """expanded_assets HTML parçasından indirme bağlantılarını çıkarır.

    Yalnızca bu deponun releases/download öneki taşıyan bağlantılar kabul
    edilir: sayfaya karışmış başka bir depo/host bağlantısı indirme adresi
    olarak kullanılamaz (URL enjeksiyonuna kapalı). Boyut ve sha256 özeti bu
    yolda gelmez; indirme sırasında Content-Length ile doğrulanır.
    """
    assets = []
    seen = set()
    for href in re.findall(r'href="([^"]+/releases/download/[^"]+)"', html or ""):
        full = urllib.parse.urljoin("https://github.com/", href)
        if not full.startswith(DOWNLOAD_PREFIX):
            continue
        name = urllib.parse.unquote(full.rsplit("/", 1)[-1])
        if not name or name in seen:
            continue
        seen.add(name)
        assets.append({"name": name, "browser_download_url": full,
                       "size": 0, "digest": ""})
    return assets


def _fetch_assets_via_page(tag, timeout_s=8):
    """Etikete ait asset bağlantılarını API'siz alır (expanded_assets parçası)."""
    url = ASSETS_FRAGMENT % urllib.parse.quote(tag, safe="")
    req = urllib.request.Request(
        url, headers={"User-Agent": "HRMA-UpdateChecker/" + __version__}
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return parse_asset_links(html)


def _fetch_notes_via_atom(tag, timeout_s=8):
    """Yayın notlarını API'siz alır (Atom akışı). Başarısızsa boş döner."""
    try:
        import xml.etree.ElementTree as ET
        req = urllib.request.Request(
            RELEASES_ATOM,
            headers={"User-Agent": "HRMA-UpdateChecker/" + __version__},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            root = ET.fromstring(resp.read())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            entry_id = (entry.findtext("a:id", "", ns) or "")
            link = entry.find("a:link", ns)
            href = (link.get("href") if link is not None else "") or ""
            if entry_id.endswith("/" + tag) or href.endswith("/" + tag):
                content = entry.findtext("a:content", "", ns) or ""
                text = re.sub(r"<[^>]+>", "", content)  # kaba HTML temizliği
                # Kırpma dil bölümü başına yapılır; Atom yolunda im yoktur,
                # bölümler sürüm başlıklarından ayrılır.
                return clip_notes(re.sub(r"\n{3,}", "\n\n", text).strip())
    except Exception:
        pass
    return ""


def _fetch_latest_release_fallback():
    """API kotası dolduğunda/API ulaşılamadığında devreye giren yol.

    GitHub'ın normal web sayfası uçlarını kullanır; dönen sözlük API
    yanıtıyla aynı alanları taşır (draft/prerelease burada yapısal olarak
    imkânsızdır: /releases/latest zaten taslak ve ön sürümleri atlar).
    """
    tag = _fetch_tag_via_page()
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": "https://github.com/%s/releases/tag/%s" % (
            GITHUB_REPO, urllib.parse.quote(tag, safe="")),
        "assets": _fetch_assets_via_page(tag),
        "body": "",
        "_source": "page",
    }


def check_for_update(force=False):
    """Güncelleme durumunu döndürür; sonuç CACHE_TTL_S boyunca önbellekli.

    Dönen sözlük her zaman aynı şemadadır:
    {available, current, latest, notes, page_url, asset, error, error_kind,
     source}
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
        # Arayüz kullanıcıya doğru cümleyi kurabilsin diye hatanın türü:
        # "rate_limit" (kota doldu, biraz sonra düzelir) / "network" (ağ yok)
        "error_kind": None,
        # Sonucun hangi yoldan geldiği: "api" | "page" (yedek) | None (hata)
        "source": None,
    }
    api_error = None
    try:
        release = _fetch_latest_release()
        result["source"] = "api"
    except Exception as exc:  # ağ yok / kota / 404 (hiç release yok)
        api_error = exc
        # API kotası dolu ya da API'ye ulaşılamıyor → sayfa yoluna düş.
        # Bu yol API kotasına tabi değildir; kullanıcı güncellemeyi görür.
        try:
            release = _fetch_latest_release_fallback()
            result["source"] = "page"
        except Exception as exc2:
            rate = _is_rate_limited(api_error)
            result["error"] = "%s: %s" % (type(api_error).__name__, api_error)
            result["error_kind"] = "rate_limit" if rate else "network"
            # Yedek yol da başarısızsa ikinci hatayı da taşı (teşhis için)
            result["error_fallback"] = "%s: %s" % (type(exc2).__name__, exc2)
            release = None

    if release is not None:
        tag = release.get("tag_name") or release.get("name") or ""
        result["latest"] = tag
        if is_newer(tag) and not release.get("draft") and not release.get("prerelease"):
            result["available"] = True
            govde = release.get("body") or ""
            result["notes"] = clip_notes(govde)
            # Dile AYRILMIŞ alanlar: istemcinin tercih ettiği yol
            # (update_check.js -> notesForActiveLang). Bölme kırpmadan ÖNCE
            # yapıldığı için uzun notlarda da doğru dil ulaşır.
            for _kod, _metin in split_notes_by_language(govde).items():
                result["notes_" + _kod] = _metin[:NOTES_MAX_CHARS]
            result["page_url"] = release.get("html_url") or RELEASES_PAGE
            result["asset"] = pick_asset(release.get("assets"))
            # Yedek yolda API notları gelmez; Atom akışından tamamla
            if not result["notes"] and result["source"] == "page":
                result["notes"] = _fetch_notes_via_atom(tag)

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


def _cleanup_stale_downloads(keep=""):
    """Yarım kalmış .download dosyalarını siler.

    Uygulama indirme sürerken kapatılırsa (güncelleme akışında olağan) yarım
    dosya İndirilenler klasöründe kalıyordu; kullanıcı bunu bozuk bir kurulum
    dosyası sanabilir (2026-07-24 saha gözlemi).
    """
    try:
        d = _downloads_dir()
        for fname in os.listdir(d):
            if (fname.startswith("HRMA-") and fname.endswith(".download")
                    and fname != keep):
                try:
                    os.remove(os.path.join(d, fname))
                except OSError:
                    pass
    except OSError:
        pass


def _run_download(url, name, size, digest=""):
    tmp_path = os.path.join(_downloads_dir(), name + ".download")
    final_path = os.path.join(_downloads_dir(), name)
    _cleanup_stale_downloads(keep=os.path.basename(tmp_path))
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
