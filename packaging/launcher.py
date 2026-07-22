#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HRMA masaüstü başlatıcı (Windows kurulumu ve macOS .app paketi ortak).

Açılış stratejisi (2026-07-14 hız + yerel pencere reformu):
1. Boş port bulunur, waitress ANINDA hafif bir WSGI shim ile başlatılır:
   shim, uygulama yüklenene kadar her isteğe koyu temalı bir "başlatılıyor"
   (splash) sayfası döner; /health ile hazır olma durumu sorgulanır.
2. Ağır importlar (hrma.app: numpy, scipy, plotly, OCC...) ARKA PLAN
   thread'inde yapılır; bitince shim gerçek Flask uygulamasına devreder,
   splash sayfası kendini yeniler.
3. Pencere pywebview ile YEREL olarak açılır (macOS: WKWebView,
   Windows: Edge WebView2) — Chrome'a gidilmez. pywebview yoksa/başarısızsa
   sırasıyla Chromium --app penceresi ve varsayılan tarayıcı sekmesine düşülür.
4. Pencere kapanınca süreç (ve sunucu) kapanır — gerçek uygulama davranışı.

Diğer görevler:
- Paket içindeki libs/ dizinini sys.path'e ekler (.pth dosyaları dahil)
- Çıktı dizinini Belgeler/HRMA altına kurar (cad_exports oraya yazılır)
- HRMA zaten çalışıyorsa ikinci kopya başlatmaz, mevcut sunucuya pencere açar
"""

import os
import sys
import site
import json
import time
import socket
import shutil
import threading
import traceback
import subprocess
import webbrowser
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LIBS_DIR = os.path.abspath(os.path.join(APP_DIR, os.pardir, "libs"))

HRMA_APP_NAME = "HRMA"
APP_COPYRIGHT = "© 2026 Berke Tezgöçen — UZAYTEK"
GITHUB_URL = "https://github.com/berketez/HRMA"
PENCERE_BASLIK = "HRMA — UZAYTEK Rocket Motor Analysis"


def _hrma_version():
    """Sürümü tek kaynaktan (hrma/__init__.py) okur; _setup_paths sonrası çağrılmalı."""
    try:
        import hrma
        return getattr(hrma, "__version__", "") or ""
    except Exception:
        return ""


def _pencere_baslik(version):
    if version:
        return "HRMA v%s — UZAYTEK Rocket Motor Analysis" % version
    return PENCERE_BASLIK

# Gerçek uygulama yüklenene kadar durum: {"wsgi": Flask|None, "error": str|None}
_app_state = {"wsgi": None, "error": None, "started_at": time.time()}


def _setup_paths():
    if os.path.isdir(LIBS_DIR):
        site.addsitedir(LIBS_DIR)
        # libs sistem paketlerinin önüne geçsin
        if LIBS_DIR in sys.path:
            sys.path.remove(LIBS_DIR)
        sys.path.insert(0, LIBS_DIR)
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)


def _setup_console():
    # Konsolsuz çalışıyorsak (pythonw / arka plan) çıktı log dosyasına gitsin
    if sys.stdout is None or sys.stderr is None:
        try:
            log = open(os.path.join(_outputs_dir(), "hrma_log.txt"),
                       "a", buffering=1, encoding="utf-8", errors="replace")
            sys.stdout = sys.stderr = log
        except Exception:
            import io
            sys.stdout = sys.stderr = io.StringIO()
        return
    if os.name == "nt":
        os.system("title HRMA - UZAYTEK Rocket Motor Analysis")
        os.system("chcp 65001 >nul")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _outputs_dir():
    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    base = docs if os.path.isdir(docs) else home
    out = os.path.join(base, "HRMA")
    os.makedirs(os.path.join(out, "cad_exports"), exist_ok=True)
    return out


def _hrma_responding(port):
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:%d/" % port, timeout=2
        ) as resp:
            return b"HRMA" in resp.read(65536)
    except Exception:
        return False


def _pick_port():
    """(port, zaten_calisiyor) döndürür."""
    forced = os.environ.get("HRMA_PORT")
    if forced:
        port = int(forced)
        return port, _hrma_responding(port)
    for port in range(8080, 8091):
        if _hrma_responding(port):
            return port, True
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return port, False
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError("No free port available in range 8080-8090.")


# ---------------------------------------------------------------------------
# Splash + shim: pencere ANINDA açılır, ağır yükleme arkada sürer
# ---------------------------------------------------------------------------

SPLASH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Starting HRMA…</title>
<style>
  html, body { height: 100%; margin: 0; }
  html { background: #04070d; } /* overscroll'da beyaz alan görünmesin */
  body {
    display: flex; align-items: center; justify-content: center;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #cfe8f2;
    background:
      radial-gradient(1100px 520px at 85% -10%, rgba(0,140,200,0.15), transparent 60%),
      radial-gradient(900px 620px at -10% 30%, rgba(0,90,160,0.10), transparent 55%),
      linear-gradient(165deg, #04070d 0%, #0a1322 60%, #070d18 100%);
  }
  .kutu { text-align: center; max-width: 420px; padding: 24px; }
  .logo { font-size: 34px; font-weight: 800; letter-spacing: 6px; color: #00e5ff;
          text-shadow: 0 0 18px rgba(0,229,255,0.35); margin-bottom: 6px; }
  .alt { font-size: 12px; letter-spacing: 2px; color: #7d97a5; margin-bottom: 34px; }
  .halka { width: 46px; height: 46px; margin: 0 auto 22px;
           border: 3px solid rgba(0,229,255,0.15); border-top-color: #00e5ff;
           border-radius: 50%; animation: don 0.9s linear infinite; }
  @keyframes don { to { transform: rotate(360deg); } }
  .durum { font-size: 14px; color: #eaf7fb; margin-bottom: 8px; }
  .ipucu { font-size: 12px; color: #46606d; line-height: 1.6; }
  .hata { display: none; font-size: 12px; color: #ff5d73; text-align: left;
          white-space: pre-wrap; max-height: 180px; overflow: auto;
          background: rgba(6,14,26,0.85); border: 1px solid rgba(255,93,115,0.4);
          border-radius: 8px; padding: 12px; margin-top: 16px; }
</style>
</head>
<body>
  <div class="kutu">
    <div class="logo">HRMA</div>
    <div class="alt">UZAYTEK ROCKET MOTOR ANALYSIS __HRMA_VERSION__</div>
    <div class="halka" id="halka"></div>
    <div class="durum" id="durum">Starting…</div>
    <div class="ipucu" id="ipucu">Loading computation engines.</div>
    <div class="hata" id="hata"></div>
  </div>
<script>
  var t0 = Date.now();
  var ipuclari = [
    "Loading computation engines.",
    "Preparing thermochemistry databases.",
    "Loading CAD kernel (OpenCascade).",
    "Almost ready…"
  ];
  var i = 0;
  setInterval(function () {
    var sn = Math.round((Date.now() - t0) / 1000);
    document.getElementById('durum').textContent = 'Starting… (' + sn + ' s)';
    if (sn > 0 && sn % 4 === 0) {
      i = Math.min(i + 1, ipuclari.length - 1);
      document.getElementById('ipucu').textContent = ipuclari[i];
    }
  }, 1000);
  function kontrol() {
    fetch('/health', {cache: 'no-store'})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ready) { location.replace('/'); return; }
        if (d.error) {
          document.getElementById('halka').style.display = 'none';
          document.getElementById('durum').textContent = 'Startup error';
          document.getElementById('ipucu').textContent =
            'Details below — you can send this text to support.';
          var h = document.getElementById('hata');
          h.style.display = 'block';
          h.textContent = d.error;
          return;
        }
        setTimeout(kontrol, 600);
      })
      .catch(function () { setTimeout(kontrol, 600); });
  }
  setTimeout(kontrol, 400);
</script>
</body>
</html>"""


def _shim_app(environ, start_response):
    """Gerçek uygulama yüklenene kadar splash + /health servis eden WSGI shim."""
    path = environ.get("PATH_INFO", "/")
    if path == "/health":
        body = json.dumps({
            "ready": _app_state["wsgi"] is not None,
            "error": _app_state["error"],
            "elapsed_s": round(time.time() - _app_state["started_at"], 1),
        }).encode("utf-8")
        start_response("200 OK", [
            ("Content-Type", "application/json"),
            ("Cache-Control", "no-store"),
            ("Content-Length", str(len(body))),
        ])
        return [body]

    real = _app_state["wsgi"]
    if real is not None:
        return real(environ, start_response)

    ver = _app_state.get("version") or ""
    body = SPLASH_HTML.replace(
        "__HRMA_VERSION__", ("· v" + ver) if ver else ""
    ).encode("utf-8")
    start_response("200 OK", [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Cache-Control", "no-store"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def _load_real_app():
    """Ağır importları arka planda yapar; bitince shim devreder."""
    t0 = time.time()
    try:
        from hrma.app import app as flask_app
        _app_state["wsgi"] = flask_app
        print("  Application loaded (%.1f s)." % (time.time() - t0))
    except Exception:
        _app_state["error"] = traceback.format_exc()
        print("  APPLICATION FAILED TO LOAD:\n%s" % _app_state["error"])


def _wait_for_port(port, timeout_s=15):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# macOS uygulama kimliği: menü çubuğu + About paneli
# ---------------------------------------------------------------------------

def _macos_app_identity(version):
    """Menü çubuğu ve About paneli 'Python 3.12' değil HRMA kimliği göstersin.

    .app içindeki gerçek yürütücü Resources/python/bin/python3.12 olduğundan
    NSBundle.mainBundle() bizim Info.plist'i bulamıyor; AppKit de menüde ve
    About panelinde Python kimliği gösteriyordu (2026-07-15 şikayeti).
    Bilgi sözlüğü süreç içinde yamalanır — NSApplication OLUŞMADAN ÖNCE
    (webview.start'tan önce) çağrılmalı.
    """
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        if bundle is None:
            return
        for info in (bundle.infoDictionary(), bundle.localizedInfoDictionary()):
            if info is None:
                continue
            info["CFBundleName"] = HRMA_APP_NAME
            info["CFBundleDisplayName"] = HRMA_APP_NAME
            if version:
                info["CFBundleShortVersionString"] = version
                info["CFBundleVersion"] = version
            info["NSHumanReadableCopyright"] = APP_COPYRIGHT
    except Exception:
        traceback.print_exc()  # kozmetik — pencere açılışını engelleme
    try:
        # About paneli ve Dock, paketsiz python sürecinde varsayılan (boş/
        # Python) simgeye düşer; bundle'daki icon.icns'i elle veriyoruz.
        # .app'te launcher Resources/app/ altında, ikon Resources/ kökünde.
        import AppKit
        icon_path = os.path.abspath(os.path.join(APP_DIR, os.pardir, "icon.icns"))
        if os.path.isfile(icon_path):
            img = AppKit.NSImage.alloc().initWithContentsOfFile_(icon_path)
            if img:
                AppKit.NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass


def _menu_check_updates():
    """macOS menüsü 'Check for Updates…' — arayüzdeki denetimi zorla tetikler."""
    try:
        import webview
        if webview.windows:
            webview.windows[0].evaluate_js(
                "window.hrmaCheckForUpdates && window.hrmaCheckForUpdates(true)")
    except Exception:
        traceback.print_exc()


def _menu_open_outputs():
    """Çıktı klasörünü işletim sisteminin dosya yöneticisinde açar (çapraz platform).

    macOS 'open', Windows os.startfile, diğerlerinde 'xdg-open'. Windows menü
    ögesi de bu işlevi çağırdığından tek platforma bağlı kalamaz."""
    out = _outputs_dir()
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", out])
        elif os.name == "nt":
            os.startfile(out)  # noqa: S606  # yalnız Windows'ta tanımlı
        else:
            subprocess.Popen(["xdg-open", out])
    except Exception:
        traceback.print_exc()


def _menu_release_notes():
    """macOS Help menüsü 'Release Notes…' — arayüzdeki sürüm notları modalını açar."""
    try:
        import webview
        if webview.windows:
            webview.windows[0].evaluate_js(
                "window.hrmaShowReleaseNotes && window.hrmaShowReleaseNotes()")
    except Exception:
        traceback.print_exc()


def _macos_menu():
    """Uygulama menüsüne HRMA'ya özgü ögeler (About'un hemen altına) + Help.

    Yalnız macOS'ta kullanılır; pywebview '__app__' başlıklı menünün
    ögelerini uygulama menüsüne (About ile Services arasına) yerleştirir.
    """
    if sys.platform != "darwin":
        return None
    try:
        import webview.menu as wm
    except Exception:
        return None
    return [
        wm.Menu("__app__", [
            wm.MenuAction("Check for Updates…", _menu_check_updates),
            wm.MenuAction("Open Output Folder", _menu_open_outputs),
        ]),
        wm.Menu("Help", [
            wm.MenuAction("Release Notes…", _menu_release_notes),
            wm.MenuAction("HRMA on GitHub",
                          lambda: webbrowser.open(GITHUB_URL)),
            wm.MenuAction("Releases and Downloads",
                          lambda: webbrowser.open(GITHUB_URL + "/releases/latest")),
        ]),
    ]


def _windows_menu():
    """Windows menü çubuğu (pencereye tutturulan MenuStrip).

    pywebview winforms arka ucu (set_window_menu) '__app__' başlıklı menüyü
    yok sayar — o yalnız macOS uygulama menüsü kavramıdır. Bu yüzden macOS'ta
    uygulama menüsüne konan eylemler (Check for Updates, Open Output Folder)
    Windows'ta GÖRÜNÜR bir 'HRMA' üst menüsüne alınır; 'Help' menüsü ise
    olduğu gibi görünür (düzenli başlıklı menüler winforms tarafından
    render edilir). webview.start(menu=...) ile verilir.
    """
    if os.name != "nt":
        return None
    try:
        import webview.menu as wm
    except Exception:
        return None
    return [
        wm.Menu("HRMA", [
            wm.MenuAction("Check for Updates…", _menu_check_updates),
            wm.MenuAction("Open Output Folder", _menu_open_outputs),
        ]),
        wm.Menu("Help", [
            wm.MenuAction("Release Notes…", _menu_release_notes),
            wm.MenuAction("HRMA on GitHub",
                          lambda: webbrowser.open(GITHUB_URL)),
            wm.MenuAction("Releases and Downloads",
                          lambda: webbrowser.open(GITHUB_URL + "/releases/latest")),
        ]),
    ]


def _native_menu():
    """Platforma göre yerel pencere menüsü döndürür.

    macOS: uygulama menüsü (__app__) + Help — mevcut davranış.
    Windows: görünür HRMA + Help menü çubuğu.
    Diğer (Linux vb.): menü verilmez (None) — eski davranış korunur.
    """
    if sys.platform == "darwin":
        return _macos_menu()
    if os.name == "nt":
        return _windows_menu()
    return None


# ---------------------------------------------------------------------------
# Pencere: pywebview (yerel) → Chromium --app → tarayıcı sekmesi
# ---------------------------------------------------------------------------

def _ui_profile_dir():
    """HRMA uygulama penceresi için AYRI profil/depolama dizini.

    pywebview'de localStorage kalıcılığı (private_mode=False + storage_path),
    Chromium fallback'inde ise --user-data-dir için kullanılır. Chromium'da
    ayrı profil şart: Chrome zaten açıkken --app parametresi yoksa mevcut
    pencereye sekme olarak yönlendiriliyor (2026-07-13 tespiti).
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        d = os.path.join(base, "HRMA", "ui-profile")
    else:
        d = os.path.expanduser("~/Library/Application Support/HRMA/ui-profile")
    os.makedirs(d, exist_ok=True)
    return d


def _try_native_window(url):
    """Yerel pencere (pywebview): macOS WKWebView / Windows Edge WebView2.

    Chrome kurulu olması GEREKMEZ. Pencere kapanana kadar bloklar;
    başarıyla açıldıysa True, hiç açılamadıysa False döner.
    """
    try:
        import webview
    except Exception as exc:
        print("  pywebview unavailable (%s) — falling back to Chromium window." % exc)
        return False
    try:
        version = _hrma_version()
        # NSApplication oluşmadan ÖNCE: menü çubuğu/About kimliği (macOS)
        _macos_app_identity(version)
        # CAD/rapor indirmeleri (blob) için indirme izni şart
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True
        except Exception:
            pass
        webview.create_window(
            _pencere_baslik(version), url,
            width=1440, height=900, min_size=(1100, 700),
            # Yerel pencerenin zemini: içerik yüklenmeden önceki an ve
            # kaydırma taşması (overscroll) beyaz parlamasın (2026-07-21)
            background_color="#04070d",
        )
        kwargs = {"private_mode": False, "storage_path": _ui_profile_dir()}
        if os.name == "nt":
            # WebView2 dışındaki eski motorlara (mshtml vb.) düşülmesin
            kwargs["gui"] = "edgechromium"
        menu = _native_menu()
        if menu:
            kwargs["menu"] = menu
        webview.start(**kwargs)
        return True  # pencere kapatıldı
    except Exception:
        print("  Native window failed, falling back to Chromium:")
        traceback.print_exc()
        return False


def _open_app_window(url):
    """Yedek 1: Chromium ailesi --app penceresi (Chrome/Edge/Brave kuruluysa).

    Başarıda pencereye ait Popen döndürür (süreç = pencere ömrü);
    Chromium ailesi yoksa None döner, çağıran tarayıcı sekmesine düşer.
    """
    flags = ["--user-data-dir=" + _ui_profile_dir(), "--app=" + url,
             "--no-first-run", "--no-default-browser-check"]
    try:
        if sys.platform == "darwin":
            for app_name in ("Google Chrome", "Microsoft Edge",
                             "Brave Browser", "Chromium"):
                binary = "/Applications/%s.app/Contents/MacOS/%s" % (
                    app_name, app_name)
                if os.path.isfile(binary):
                    return subprocess.Popen([binary] + flags)
        elif os.name == "nt":
            adaylar = [shutil.which(e) for e in ("msedge", "chrome", "brave")]
            adaylar += [os.path.expandvars(p) for p in (
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
            )]
            for cand in adaylar:
                if cand and os.path.isfile(cand):
                    return subprocess.Popen([cand] + flags)
    except Exception:
        pass
    return None


def _show_window_blocking(url):
    """Pencereyi açar ve KAPANANA KADAR bloklar; dönüşte süreç sonlanmalı.

    Sıra: pywebview (yerel) → Chromium --app → varsayılan tarayıcı sekmesi.
    Tarayıcı sekmesine düşüldüyse pencere ömrü izlenemez; sunucu, kullanıcı
    süreci kapatana kadar çalışır durumda bırakılır.
    """
    if os.environ.get("HRMA_NO_WINDOW"):
        # Otomatik test modu: pencere açma, sunucuyu ayakta tut
        print("  HRMA_NO_WINDOW=1 — window suppressed, server: %s" % url)
        threading.Event().wait()
        return

    if _try_native_window(url):
        return

    proc = _open_app_window(url)
    if proc is not None:
        print("  Chromium app window opened: %s" % url)
        proc.wait()
        print("  Application window closed.")
        return

    try:
        webbrowser.open(url)
        print()
        print("  HRMA opened in your browser: %s" % url)
        print("  If it did not open, type the address above manually.")
        print("  Window tracking is unavailable in this mode; end this")
        print("  process to quit (Ctrl+C / task bar).")
    except Exception:
        print("  Could not open a browser, open this address manually: %s" % url)
    threading.Event().wait()  # süreç, kullanıcı kapatana kadar yaşar


def main():
    _setup_console()
    _setup_paths()
    os.environ.setdefault("MPLBACKEND", "Agg")

    _app_state["version"] = _hrma_version()

    print("=" * 62)
    print("  HRMA - UZAYTEK Rocket Motor Analysis"
          + (" v" + _app_state["version"] if _app_state["version"] else ""))
    print("=" * 62)

    port, already_running = _pick_port()
    url = "http://127.0.0.1:%d" % port

    if already_running:
        print()
        print("  HRMA is already running, opening a window: %s" % url)
        _show_window_blocking(url)
        return

    out_dir = _outputs_dir()
    os.chdir(out_dir)

    print()
    print("  Opening window; engines are loading in the background...")
    print("  Output files (CAD, drawings): %s" % out_dir)
    print("  Closing the HRMA window also closes the program.")
    print()

    # 1) Ağır importlar arka planda
    threading.Thread(target=_load_real_app, daemon=True).start()

    # 2) Sunucu ANINDA kalkar (shim: splash + /health)
    from waitress import serve
    threading.Thread(
        target=lambda: serve(_shim_app, host="127.0.0.1", port=port, threads=8),
        daemon=True,
    ).start()

    # 3) Port dinlemeye geçer geçmez pencereyi aç (splash görünür)
    _wait_for_port(port)

    # Güvence: portta BİZİM shim mi konuşuyor? (HRMA_PORT zorlanmış ve port
    # başka bir sunucudaysa pencereyi yabancı içeriğe açma — 2026-07-14 denetimi)
    try:
        with urllib.request.urlopen(url + "/health", timeout=3) as resp:
            json.loads(resp.read())["ready"]
    except Exception:
        print("  HATA: %s beklenen HRMA sunucusu değil (port çakışması?)." % url)
        print("  HRMA_PORT ayarını kaldırın veya boş bir port verin.")
        sys.exit(1)

    _show_window_blocking(url)

    # Pencere kapandı → sunucu daemon thread'leriyle birlikte kapan
    print("  Shutting down HRMA...")
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down HRMA...")
    except Exception:
        print("\nAn error occurred:\n")
        traceback.print_exc()
        print("\nYou can send this file to support: Documents/HRMA/hrma_log.txt")
        if os.name == "nt":
            # pythonw ile konsol yok — hatayı iletişim kutusuyla göster
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0, "HRMA could not start.\n\nDetails: Documents\\HRMA\\"
                       "hrma_log.txt\n\n" + traceback.format_exc()[-900:],
                    "HRMA - Error", 0x10)
            except Exception:
                pass
        try:
            if sys.stdin is not None and sys.stdin.isatty():
                input("Press Enter to close...")
        except Exception:
            pass
        sys.exit(1)
