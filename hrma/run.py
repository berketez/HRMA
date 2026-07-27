#!/usr/bin/env python3
"""
Rocket Motor Analysis Web Application
Cross-platform launcher script (Windows/Mac/Linux)
"""

import os
import socket
import sys
import platform
import webbrowser
import time
from threading import Timer

# Betik hrma/ içinde yaşıyor: 'import hrma' için depo kökü sys.path'e eklenir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Taranacak port aralığı — packaging/launcher.py::_pick_port ile AYNI olmalı.
#: tests/test_local_api_security.py bu iki dosyanın ayrışmasını yakalar.
PORT_RANGE = range(8080, 8091)


def pick_port():
    """Aralıktaki ilk boş portu döndürür.

    v2.6.25 — NEDEN: burada eskiden üç ayrı yerde sabit 8080 vardı. 8080'i
    başka bir uygulama tutuyorsa sunucu ``OSError: Address already in use``
    ile çöküyordu; üstelik tarayıcı zamanlayıcısı çökmeden önce kurulduğu
    için kullanıcının önüne 8080'deki YABANCI uygulama açılıyordu. Masaüstü
    başlatıcısı (packaging/launcher.py) zaten boş port arıyordu; bu dosya
    o davranıştan habersizdi — v2.6.2'yi kullanılamaz yapan CORS hatasıyla
    birebir aynı kalıp: aynı bilgi iki dosyada, biri diğerini bilmiyor.
    """
    for port in PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        "8080-8090 aralığında boş port yok. Bu portları tutan uygulamaları "
        "kapatın ya da HRMA_PORT ile bir port belirtin.")


def open_browser(port):
    """Open web browser after a delay"""
    time.sleep(1.5)
    try:
        webbrowser.open('http://127.0.0.1:%d' % port)
    except Exception:
        pass  # Ignore browser opening errors

def check_python_version():
    """Desteklenen Python aralığını doğrula (3.10–3.13; önerilen 3.12).

    3.14+ desteklenmez: Cantera / CoolProp / RocketCEA gibi derlenmiş
    bağımlılıkların 3.14 wheel'leri yok.
    """
    v = sys.version_info
    if v < (3, 10):
        print(f"Error: Python {v.major}.{v.minor} detected. Python 3.10+ is required (3.12 recommended).")
        sys.exit(1)
    if v >= (3, 14):
        print(f"Error: Python {v.major}.{v.minor} is not supported yet (compiled dependencies "
              f"such as Cantera/CoolProp lack 3.14 wheels). Please use Python 3.12.")
        sys.exit(1)

def run_server():
    """Run the web server with platform-specific settings"""
    check_python_version()
    from hrma.app import app

    forced = os.environ.get("HRMA_PORT")
    port = int(forced) if forced else pick_port()

    print("=" * 60)
    print("  ROCKET MOTOR ANALYSIS WEB TOOL")
    print(f"  http://127.0.0.1:{port}")
    print("=" * 60)
    print()
    print(f"Platform: {platform.system()} {platform.release()}")
    print("Starting web server...")
    print("Press Ctrl+C to stop")
    print()

    # Open browser automatically
    Timer(1.0, open_browser, args=(port,)).start()

    # Use appropriate server for platform
    if platform.system() == "Windows":
        try:
            from waitress import serve
            print("Using Waitress server (Windows optimized)")
            serve(app, host='127.0.0.1', port=port, threads=4)
        except ImportError:
            print("Waitress not available, using Flask dev server")
            app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False)
    else:
        # Unix-like systems (Mac/Linux)
        # debug=False ZORUNLU (2026-07-23 kararlılık/güvenlik denetimi):
        # debug=True, Werkzeug etkileşimli hata ayıklayıcısını açar. O ekran
        # tarayıcıdan KEYFİ PYTHON KODU çalıştırmaya izin verir; 127.0.0.1'e
        # bağlı olsa bile aynı makinedeki herhangi bir web sayfası (DNS
        # rebinding / kurbanın tarayıcısı üzerinden) erişebilir. Windows yolu
        # zaten debug=False idi; macOS/Linux yolu açık kalmıştı.
        try:
            from gunicorn.app.wsgiapp import WSGIApplication
            print("Using Gunicorn server (Unix optimized)")
            # Note: Gunicorn setup would go here, but Flask dev server is simpler for this use case
            app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False)
        except ImportError:
            print("Using Flask dev server")
            app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False)

if __name__ == '__main__':
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nShutting down web server...")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting server: {e}")
        if platform.system() == "Windows":
            input("Press Enter to exit...")
        sys.exit(1)