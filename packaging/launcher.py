#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HRMA masaüstü başlatıcı (Windows kurulumu ve macOS .app paketi ortak).

Görevleri:
- Paket içindeki libs/ dizinini sys.path'e ekler (.pth dosyaları dahil)
- Çıktı dizinini Belgeler/HRMA altına kurar (cad_exports oraya yazılır)
- Boş port bulur (8080-8090), sunucu hazır olunca tarayıcıyı açar
- HRMA zaten çalışıyorsa ikinci kopya başlatmaz, mevcut sekmeyi açar
"""

import os
import sys
import site
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
        os.system("title HRMA - UZAYTEK Hibrit Roket Motor Analizi")
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
    raise RuntimeError("8080-8090 arasında boş port bulunamadı.")


def _ui_profile_dir():
    """HRMA uygulama penceresi için AYRI tarayıcı profili.

    Chrome/Edge zaten açıkken --app parametresi mevcut pencereye sekme
    olarak yönlendirilir (2026-07-13 tespiti). Ayrı --user-data-dir ile
    her zaman bağımsız bir süreç ve gerçek uygulama penceresi açılır;
    pencere kapanınca süreç biter → sunucu ömrü pencereye bağlanabilir.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        d = os.path.join(base, "HRMA", "ui-profile")
    else:
        d = os.path.expanduser("~/Library/Application Support/HRMA/ui-profile")
    os.makedirs(d, exist_ok=True)
    return d


def _open_app_window(url):
    """Arayüzü gerçek uygulama penceresi olarak aç (Chromium --app modu).

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


def _open_ui(url):
    """UI'yi aç; uygulama penceresi süreci varsa Popen'ını döndürür."""
    proc = _open_app_window(url)
    if proc is None:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return proc


def _bind_lifetime_to_window(proc):
    """Uygulama penceresi kapanınca sunucuyu da kapat (gerçek uygulama hissi)."""
    def _bekci():
        proc.wait()
        print("Uygulama penceresi kapatıldı, HRMA kapanıyor...")
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=_bekci, daemon=True).start()


def _open_browser_when_ready(port, timeout_s=120):
    url = "http://127.0.0.1:%d" % port
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                break
        except Exception:
            time.sleep(0.5)
    proc = _open_ui(url)
    if proc is not None:
        _bind_lifetime_to_window(proc)
    print()
    print("  HRMA penceresi açıldı: %s" % url)
    print("  Açılmadıysa yukarıdaki adresi tarayıcınıza elle yazın.")


def main():
    _setup_console()
    _setup_paths()
    os.environ.setdefault("MPLBACKEND", "Agg")

    print("=" * 62)
    print("  HRMA - UZAYTEK Hibrit Roket Motor Analizi")
    print("=" * 62)

    port, already_running = _pick_port()
    url = "http://127.0.0.1:%d" % port

    if already_running:
        print()
        print("  HRMA zaten çalışıyor, pencere açılıyor: %s" % url)
        _open_ui(url)
        time.sleep(3)
        return

    out_dir = _outputs_dir()
    os.chdir(out_dir)

    print()
    print("  Başlatılıyor, ilk açılış 10-30 saniye sürebilir...")
    print("  Çıktı dosyaları (CAD, çizimler): %s" % out_dir)
    print("  HRMA penceresini kapatınca program da kapanır.")
    print()

    from hrma.app import app  # ağır importlar burada (numpy, scipy, OCC...)

    threading.Thread(
        target=_open_browser_when_ready, args=(port,), daemon=True
    ).start()

    from waitress import serve

    serve(app, host="127.0.0.1", port=port, threads=8)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nHRMA kapatılıyor...")
    except Exception:
        print("\nBir hata oluştu:\n")
        traceback.print_exc()
        print("\nBu dosyayı destek için iletebilirsiniz: Belgeler/HRMA/hrma_log.txt")
        if os.name == "nt":
            # pythonw ile konsol yok — hatayı iletişim kutusuyla göster
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0, "HRMA başlatılamadı.\n\nAyrıntı: Belgeler\\HRMA\\"
                       "hrma_log.txt\n\n" + traceback.format_exc()[-900:],
                    "HRMA - Hata", 0x10)
            except Exception:
                pass
        try:
            if sys.stdin is not None and sys.stdin.isatty():
                input("Kapatmak için Enter tuşuna basın...")
        except Exception:
            pass
        sys.exit(1)
