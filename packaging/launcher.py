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

# Windows görev çubuğu kimliği — TEK KAYNAK. Süreç pythonw.exe olduğu için
# kabuk pencereyi varsayılan olarak "Python" altında gruplar.
WIN_APP_USER_MODEL_ID = "UZAYTEK.HRMA"

# Windows menü şeridinin koyu paleti (R, G, B) — TEK KAYNAK; renk değerleri
# başka hiçbir yerde tekrarlanmaz. Değerler arayüz temasından alındı
# (hrma/static/css/hd_doc.css + splash):
#   serit_zemin  #101a28 : --hd-bg0 (#04070d) ile --hd-bg1 (#0a1322) arası ton
#   acilir_zemin #0a1322 : --hd-bg1 birebir
#   metin        #cfe8f2 : splash/arayüz metin rengi
#   secili       #1e3046 : üzerine gelinen ögede hafif açılan ton
#   kenar        #2a3e56 : çerçeve ve ayraç
WIN_MENU_RENK = {
    "serit_zemin": (16, 26, 40),
    "acilir_zemin": (10, 19, 34),
    "metin": (207, 232, 242),
    "secili": (30, 48, 70),
    "kenar": (42, 62, 86),
}


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
        # Python) simgeye düşer; bundle'daki simgeyi elle veriyoruz.
        # .app'te launcher Resources/app/ altında, ikon Resources/ kökünde.
        #
        # v2.6.25 — NEDEN icon.icns DEĞİL de icon_runtime.png:
        # macOS 26 (Tahoe) bundle simgesine KENDİ yuvarlatılmış karo maskesini
        # uygular. Bu yüzden ``icon.icns`` artık TAM TAŞMA (kare, tuvalin
        # tamamı) üretiliyor — maskeyi sistem koyuyor (bkz. make_icons.py).
        # Ama ``setApplicationIconImage_`` o maskeyi BYPASS eder, ham görüntüyü
        # çizer; oraya tam taşma vermek Dock'ta keskin köşeli bir kare
        # gösterirdi. Çalışma anı için önceden yuvarlatılmış varlığı veriyoruz.
        import AppKit
        res_dir = os.path.abspath(os.path.join(APP_DIR, os.pardir))
        for aday in ("icon_runtime.png", "icon.icns"):
            icon_path = os.path.join(res_dir, aday)
            if not os.path.isfile(icon_path):
                continue
            img = AppKit.NSImage.alloc().initWithContentsOfFile_(icon_path)
            if img:
                AppKit.NSApplication.sharedApplication().setApplicationIconImage_(img)
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Windows pencere kimliği: görev çubuğu/başlık simgesi + koyu menü şeridi
#
# İki kusur fotoğrafla doğrulandı (2026-08-14, Berke'nin ekran görüntüsü):
#   1) Pencere başlığında ve görev çubuğunda PYTHON logosu. Kaynağı okundu:
#      pywebview'in winforms arka ucu, kendisine ikon VERİLMEZSE simgeyi
#      sys.executable'dan (yani pythonw.exe'den) ExtractIconW ile çıkarıyor
#      (site-packages/webview/platforms/winforms.py, "Application icon" bloğu).
#      Kısayoldaki hrma.ico pencereye değil kısayola aittir.
#   2) Koyu uygulamanın üstünde BEMBEYAZ WinForms MenuStrip. Kaynağı: aynı
#      dosyada menü ``WinForms.MenuStrip()`` olarak kuruluyor, hiçbir renk/
#      çizici ayarı yapılmadan ``self.Controls.Add`` ediliyor; varsayılan
#      "Professional" çizici de BackColor'ı yok sayıp açık gri gradyan çizer.
#
# Bu bölümün TAMAMI Windows'ta ÇALIŞTIRILAMADI (macOS'ta yazıldı, hedef
# makineye erişim yoktu). Bu yüzden her adım KENDİ try/except'inde: kısmi
# başarı kabul, çökme yasak. Hiçbir adım pencerenin açılmasını engelleyemez;
# başarısızlıkta davranış eskisine (Python simgesi / açık menü) düşer.
# ---------------------------------------------------------------------------

def _windows_log(mesaj):
    """Windows rötuşlarının günlüğü.

    Dosyanın günlükleme deseni ayrı bir soyutlama değil, doğrudan ``print``;
    pythonw altında konsol olmadığından _setup_console çıktıyı
    Documents/HRMA/hrma_log.txt'ye yönlendirir. Yani bu satırlar kullanıcının
    destek dosyasında görünür.
    """
    print("  windows: %s" % mesaj)


def _windows_app_identity():
    """Görev çubuğu kimliği (AppUserModelID) — PENCERE KURULMADAN ÖNCE.

    Kabuk, bir pencere ilk kez oluşturulduğunda sürecin kimliğini önbelleğe
    alır; kimlik verilmezse pythonw.exe'nin kimliği kullanılır ve HRMA görev
    çubuğunda "Python" ile aynı kutuda gruplanır. Windows'ta DOĞRULANMADI
    (2026-08-14).
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WIN_APP_USER_MODEL_ID)
    except Exception as exc:
        _windows_log("AppUserModelID ayarlanamadı (%s) — görev çubuğunda "
                     "Python altında gruplanabilir" % exc)


def _windows_icon_path():
    """hrma.ico'nun yolu; iki düzen SIRAYLA denenir, ilk VAR OLAN döner.

    1) Kurulum düzeni (packaging/hrma.nsi): launcher $INSTDIR\\app\\launcher.py,
       ikon $INSTDIR\\hrma.ico  ->  parent.parent
    2) Depo/geliştirme düzeni: packaging/launcher.py ve packaging/hrma.ico
       yan yana  ->  parent

    Bulunamazsa None; çağıranlar simgeyi sessizce atlar (pencere yine açılır).
    """
    try:
        from pathlib import Path
        kok = Path(__file__).resolve()
        for aday in (kok.parent.parent / "hrma.ico", kok.parent / "hrma.ico"):
            if aday.is_file():
                return str(aday)
    except Exception as exc:
        _windows_log("ikon yolu çözülemedi (%s)" % exc)
    return None


def _windows_forms():
    """pythonnet köprüsü: System.Windows.Forms modülü (kurulamazsa None).

    İçe aktarma ÇALIŞMA ANINDA yapılır. Modül düzeyinde ``import clr``
    yazılsaydı launcher macOS'ta import anında çökerdi — yani bu satırların
    yeri bilinçli bir kısıt, üşengeçlik değil.
    """
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Drawing")
        import System.Windows.Forms as WinForms
        return WinForms
    except Exception as exc:
        _windows_log(".NET köprüsü (pythonnet) kurulamadı (%s) — simge/menü "
                     "rötuşu atlandı" % exc)
        return None


def _windows_ana_form(WinForms):
    """Uygulamanın açık .NET formu (pywebview tek pencere açar)."""
    try:
        formlar = [f for f in WinForms.Application.OpenForms]
    except Exception as exc:
        _windows_log("Application.OpenForms okunamadı (%s)" % exc)
        return None
    if not formlar:
        _windows_log("Application.OpenForms boş — pencere henüz kurulmamış, "
                     "rötuş atlandı")
        return None
    return formlar[0]


def _windows_form_ikonu(form):
    """Pencere/görev çubuğu simgesini hrma.ico yapar (arayüz iş parçacığında).

    webview.start(icon=...) yolu form KURULURKEN aynı dosyayı veriyor; burası
    o parametreyi tanımayan pywebview sürümleri için güvence katmanıdır.
    """
    yol = _windows_icon_path()
    if not yol:
        _windows_log("hrma.ico bulunamadı — pencere simgesi pythonw.exe'den "
                     "kalır (Python logosu)")
        return
    try:
        import System.Drawing as Drawing
        form.Icon = Drawing.Icon(yol)
        form.ShowIcon = True
    except Exception as exc:
        _windows_log("pencere simgesi ayarlanamadı (%s)" % exc)


def _windows_menu_serit_bul(form):
    """Formdaki MenuStrip'i tip ADIYLA arar.

    pywebview şeridi ``self.Controls.Add(top_level_menu)`` ile ekliyor ve
    MainMenuStrip'e ATAMIYOR; yine de önce MainMenuStrip denenir (başka bir
    sürüm atayabilir). Tip adı kullanılıyor çünkü pythonnet tiplerini Python
    ``isinstance``'ıyla eşleştirmek sürümden sürüme değişebiliyor.
    """
    try:
        serit = getattr(form, "MainMenuStrip", None)
        if serit is not None:
            return serit
    except Exception:
        pass
    try:
        for ctrl in form.Controls:
            try:
                if ctrl.GetType().Name == "MenuStrip":
                    return ctrl
            except Exception:
                continue
    except Exception as exc:
        _windows_log("form.Controls gezilemedi (%s)" % exc)
    return None


def _windows_menu_ogeleri_boya(ogeler, zemin, acilir_zemin, metin, derinlik=0):
    """Üst ögeleri ve açılır menülerini aynı palete boyar (sığ özyineleme).

    Üst şerit ögeleri şerit zeminini, açılır menüler ve alt ögeleri açılır
    zemini alır. Tek bir ögenin boyanamaması diğerlerini durdurmaz.
    """
    if derinlik > 5:
        return
    for oge in ogeler:
        try:
            oge.BackColor = zemin
            oge.ForeColor = metin
        except Exception:
            pass
        try:
            acilir = getattr(oge, "DropDown", None)
        except Exception:
            acilir = None
        if acilir is None:
            continue
        try:
            acilir.BackColor = acilir_zemin
            acilir.ForeColor = metin
        except Exception:
            pass
        try:
            alt_ogeler = [o for o in oge.DropDownItems]
        except Exception:
            continue
        _windows_menu_ogeleri_boya(alt_ogeler, acilir_zemin, acilir_zemin,
                                   metin, derinlik + 1)


def _windows_koyu_cizici(WinForms, renk):
    """ProfessionalColorTable alt sınıfı + ToolStripProfessionalRenderer.

    NEDEN sanal ÖZELLİK (@property) değil de get_X YÖNTEMLERİ: pythonnet
    sürümleri sanal özellik geçersiz kılmayı farklı ele alıyor. Python
    tarafında ``@property MenuStripGradientBegin`` tanımlanırsa Python'dan
    okurken doğru renk görünür ama .NET tarafındaki sanal çağrı hâlâ TABAN
    sınıfa gidebilir — yani beyaz gradyan geri gelir ve biz bunu ölçemeyiz
    (Python özelliği ölçümü gölgeler). get_X yöntemi Python tarafında aynı
    adla bir gölge bırakmadığı için nesneden ``.MenuStripGradientBegin``
    okumak GERÇEK .NET sanal çağrısını tetikler.

    Bu yüzden çizici KANITLANMADAN kurulmaz: sınama tutmazsa None döner ve
    çağıran katman 1-2'de (düz koyu şerit) kalır. Aksi hâlde geçersiz kılması
    tutmamış bir Professional çizici, sistem çizicisinin yerine geçip beyaz
    gradyanı GERİ getirirdi — yani düzeltmeyi bozardı.

    Windows'ta DOĞRULANMADI (2026-08-14).
    """
    try:
        class _KoyuRenkTablosu(WinForms.ProfessionalColorTable):
            """MenuStrip gradyanlarının koyu karşılıkları."""

            def get_MenuStripGradientBegin(self):
                return renk["serit_zemin"]

            def get_MenuStripGradientEnd(self):
                return renk["serit_zemin"]

            def get_ToolStripDropDownBackground(self):
                return renk["acilir_zemin"]

            def get_MenuItemSelected(self):
                return renk["secili"]

            def get_MenuItemSelectedGradientBegin(self):
                return renk["secili"]

            def get_MenuItemSelectedGradientEnd(self):
                return renk["secili"]

            def get_MenuItemPressedGradientBegin(self):
                return renk["serit_zemin"]

            def get_MenuItemPressedGradientMiddle(self):
                return renk["acilir_zemin"]

            def get_MenuItemPressedGradientEnd(self):
                return renk["acilir_zemin"]

            def get_MenuBorder(self):
                return renk["kenar"]

            def get_MenuItemBorder(self):
                return renk["kenar"]

            def get_ImageMarginGradientBegin(self):
                return renk["acilir_zemin"]

            def get_ImageMarginGradientMiddle(self):
                return renk["acilir_zemin"]

            def get_ImageMarginGradientEnd(self):
                return renk["acilir_zemin"]

            def get_SeparatorDark(self):
                return renk["kenar"]

            def get_SeparatorLight(self):
                return renk["kenar"]

        tablo = _KoyuRenkTablosu()
    except Exception as exc:
        _windows_log("koyu renk tablosu kurulamadı (%s) — pythonnet bu "
                     "alt sınıflamayı desteklemiyor olabilir" % exc)
        return None

    # KANIT adımı: .NET sanal çağrısı gerçekten bize mi geliyor?
    try:
        olculen = tablo.MenuStripGradientBegin
        okunan = (int(olculen.R), int(olculen.G), int(olculen.B))
        if okunan != tuple(WIN_MENU_RENK["serit_zemin"]):
            _windows_log("çizici sınaması tutmadı (okunan %s, beklenen %s) — "
                         "özel çizici KURULMUYOR, düz koyu şerit korunuyor"
                         % (okunan, tuple(WIN_MENU_RENK["serit_zemin"])))
            return None
    except Exception as exc:
        _windows_log("çizici sınanamadı (%s) — özel çizici kurulmuyor" % exc)
        return None

    try:
        return WinForms.ToolStripProfessionalRenderer(tablo)
    except Exception as exc:
        _windows_log("Professional çizici kurulamadı (%s)" % exc)
        return None


def _windows_menu_temasi(form, WinForms):
    """Beyaz MenuStrip'i koyu temaya çeker — üç katman, her biri AYRI denenir.

    Katmanlar bilerek artan kırılganlıkta: 1. katman tutmazsa hiçbiri
    tutmaz, 3. katman tutmazsa 1-2 ayakta kalır (menü yine koyu olur, yalnız
    vurgu rengi sistemden gelir). Windows'ta DOĞRULANMADI (2026-08-14).
    """
    serit = _windows_menu_serit_bul(form)
    if serit is None:
        _windows_log("MenuStrip bulunamadı — menü teması atlandı "
                     "(menü hiç kurulmamış olabilir)")
        return
    try:
        import System.Drawing as Drawing
        renk = {ad: Drawing.Color.FromArgb(int(r), int(g), int(b))
                for ad, (r, g, b) in WIN_MENU_RENK.items()}
    except Exception as exc:
        _windows_log("renkler kurulamadı (%s) — menü teması atlandı" % exc)
        return

    # Katman 1 — düz renk. Varsayılan "Professional" çizici BackColor'ı YOK
    # SAYIP açık gri gradyan çizer; fotoğraftaki beyaz şerit tam olarak budur.
    # Sistem çizicisi BackColor'a saygı duyduğu için render kipi de
    # değiştirilir: 3. katman (özel çizici) tutmasa bile şerit koyu kalır.
    try:
        serit.BackColor = renk["serit_zemin"]
        serit.ForeColor = renk["metin"]
    except Exception as exc:
        _windows_log("şerit rengi verilemedi (%s)" % exc)
    try:
        serit.RenderMode = WinForms.ToolStripRenderMode.System
    except Exception as exc:
        _windows_log("render kipi Sistem'e alınamadı (%s)" % exc)
    try:
        # Görsel stiller açıkken sistem çizicisi menüyü yine tema renkleriyle
        # boyayabiliyor. Bu bayrak yalnız bu sürecin ToolStrip'lerini etkiler.
        WinForms.ToolStripManager.VisualStylesEnabled = False
    except Exception as exc:
        _windows_log("VisualStylesEnabled kapatılamadı (%s)" % exc)

    # Katman 2 — üst ögeler ve açılır menüler
    try:
        ust_ogeler = [o for o in serit.Items]
    except Exception as exc:
        _windows_log("menü ögeleri okunamadı (%s)" % exc)
        ust_ogeler = []
    try:
        _windows_menu_ogeleri_boya(ust_ogeler, renk["serit_zemin"],
                                   renk["acilir_zemin"], renk["metin"])
    except Exception as exc:
        _windows_log("menü ögeleri boyanamadı (%s)" % exc)

    # Katman 3 — özel çizici (yalnız KANITLANIRSA kurulur, bkz. _windows_koyu_cizici)
    cizici = _windows_koyu_cizici(WinForms, renk)
    if cizici is None:
        _windows_log("özel çizici doğrulanamadı — katman 1-2 ile yetinildi "
                     "(şerit koyu, vurgu rengi sistemden)")
        return
    try:
        serit.Renderer = cizici
    except Exception as exc:
        _windows_log("çizici şeride verilemedi (%s)" % exc)
        return
    try:
        # Açılır menüler çizicilerini yöneticiden alabiliyor; aynı çizici
        # verilmezse şerit koyu, açılır menü açık kalabilir.
        WinForms.ToolStripManager.Renderer = cizici
    except Exception as exc:
        _windows_log("çizici yöneticiye verilemedi (%s)" % exc)


def _windows_chrome_fix():
    """Pencere ikonu + menü şeridinin koyu teması (pythonnet/.NET).

    Windows'ta DOĞRULANMADI (2026-08-14): hedef makineye erişim yok; her adım
    kendi try/except'inde — kısmi başarı kabul, çökme yasak. Pencere
    GÖRÜNDÜKTEN sonra çağrılır (events.shown), bu yüzden .NET formu
    Application.OpenForms içinde hazırdır.
    """
    if os.name != "nt":
        return
    WinForms = _windows_forms()
    if WinForms is None:
        return
    form = _windows_ana_form(WinForms)
    if form is None:
        return

    def _uygula():
        _windows_form_ikonu(form)
        _windows_menu_temasi(form, WinForms)

    # pywebview 'shown' işleyicilerini AYRI bir iş parçacığında çalıştırıyor
    # (webview/event.py: Event(window) -> should_lock=False -> threading.Thread).
    # WinForms denetimleri kendi iş parçacığından değiştirilmelidir; yoksa
    # cross-thread istisnası ya da sessiz bozulma olur. BeginInvoke seçildi
    # (Invoke değil): geri dönüşü beklemediğimiz için kilitlenme riski yok.
    try:
        if form.InvokeRequired:
            from System import Action
            form.BeginInvoke(Action(_uygula))
            return
    except Exception as exc:
        _windows_log("arayüz iş parçacığına geçilemedi (%s) — doğrudan "
                     "deneniyor" % exc)
    try:
        _uygula()
    except Exception:
        traceback.print_exc()  # kozmetik — pencereyi ASLA engelleme


def _windows_chrome_fix_gecikmeli():
    """Yedek kanca (webview.start(func=...)) için gecikmeli rötuş.

    start(func=...) pencere kurulmadan ÖNCE de tetiklenebildiğinden form
    listesi dolana kadar kısa süre beklenir; dolmazsa _windows_chrome_fix
    zaten "OpenForms boş" diyip sessizce çıkar.
    """
    if os.name != "nt":
        return
    for _ in range(50):  # ~10 s
        WinForms = _windows_forms()
        if WinForms is None:
            return
        try:
            if len(WinForms.Application.OpenForms) > 0:
                break
        except Exception:
            pass
        time.sleep(0.2)
    _windows_chrome_fix()


def _windows_chrome_kancasi(pencere):
    """Rötuşu pencerenin 'shown' olayına bağlar; başarıda True.

    'shown' tercih ediliyor çünkü TAM olarak form gösterildikten sonra
    tetikleniyor — o anda Application.OpenForms dolu. webview.start(func=...)
    ise pencere kurulmadan da çalışabildiği için (yarış) yalnız yedek.
    """
    try:
        pencere.events.shown += _windows_chrome_fix
        return True
    except Exception as exc:
        _windows_log("'shown' kancasına bağlanılamadı (%s) — start(func=...) "
                     "yedeğine düşülüyor" % exc)
        return False


def _webview_start_ikonu_destekliyor(webview):
    """Bu pywebview sürümü start(icon=...) parametresini tanıyor mu?

    6.2.1 tanıyor (paketleme bu sürümü sabitliyor); eski sürümlerde bilinmeyen
    anahtar TypeError verip yerel pencere açılışını komple düşürürdü.
    """
    try:
        import inspect
        return "icon" in inspect.signature(webview.start).parameters
    except Exception:
        return False


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
        pencere = webview.create_window(
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
            # Pencere simgesi — DESTEKLENEN yol: pywebview'in winforms arka ucu
            # kendisine ikon verilmezse simgeyi sys.executable'dan (pythonw.exe)
            # çıkarıyor; başlıktaki Python logosunun kaynağı bu. Parametreyle
            # verildiğinde simge form KURULURKEN, yani pencere görünmeden önce
            # yerine oturur. _windows_chrome_fix ayrıca pencere göründükten
            # sonra da basar (parametreyi tanımayan sürümler için güvence).
            ico = _windows_icon_path()
            if ico and _webview_start_ikonu_destekliyor(webview):
                kwargs["icon"] = ico
            # Koyu menü + simge güvencesi: pencere göründükten SONRA .NET rötuşu.
            # 'shown' kancası kurulamazsa start(func=...) yedeğine düşülür.
            if not _windows_chrome_kancasi(pencere):
                kwargs["func"] = _windows_chrome_fix_gecikmeli
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
    # Windows görev çubuğu kimliği HİÇBİR pencere kurulmadan önce verilmeli
    # (kabuk kimliği ilk pencerede önbelleğe alıyor). Bu işlev tüm pencere
    # yollarının TEK geçidi olduğu için çağrı buranın en başında duruyor;
    # macOS/Linux'ta işlevin kendisi ilk satırda çıkar.
    _windows_app_identity()

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

    # Köken kapısına gerçekte bağlandığımız portu bildir (hrma/app.py bunu
    # import anında app.config['HRMA_SELF_PORT'] içine alır). Bilinmezse kapı
    # 127.0.0.1'in HERHANGİ bir portundan gelen isteği kabul etmek zorunda
    # kalıyordu — yerel bir geliştirme sunucusu ya da kötü niyetli yerel
    # uygulama bu boşluktan CSRF yapabiliyordu.
    os.environ["HRMA_SELF_PORT"] = str(port)

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
