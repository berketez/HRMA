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
import threading
import traceback
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


def _open_browser_when_ready(port, timeout_s=120):
    url = "http://127.0.0.1:%d" % port
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                break
        except Exception:
            time.sleep(0.5)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print()
    print("  Tarayıcı açıldı: %s" % url)
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
        print("  HRMA zaten çalışıyor, tarayıcı açılıyor: %s" % url)
        webbrowser.open(url)
        time.sleep(3)
        return

    out_dir = _outputs_dir()
    os.chdir(out_dir)

    print()
    print("  Başlatılıyor, ilk açılış 10-30 saniye sürebilir...")
    print("  Çıktı dosyaları (CAD, çizimler): %s" % out_dir)
    print()
    print("  BU PENCEREYİ KAPATIRSANIZ HRMA KAPANIR.")
    print("  Kullanırken bu pencereyi küçültüp açık bırakın.")
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
        print("\nBu ekranın fotoğrafını çekip destek için iletebilirsiniz.")
        try:
            input("Kapatmak için Enter tuşuna basın...")
        except Exception:
            pass
        sys.exit(1)
