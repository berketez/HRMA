#!/usr/bin/env python
"""
Windows-optimized launcher for Rocket Motor Analysis Tool
Includes enhanced error handling and Windows-specific optimizations
"""

import os
import sys
import platform
import webbrowser
import time
import subprocess
from threading import Timer

# Betik hrma/ içinde: 'import hrma' için depo kökü sys.path'e eklenir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def clear_screen():
    """Clear the console screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def check_dependencies():
    """Check if all required packages are installed"""
    required_packages = [
        'flask',
        'flask_cors', 
        'numpy',
        'scipy',
        'plotly',
        'pandas',
        'waitress'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    return missing

#: Deponun PİNLİ bağımlılık listesi — TEK KURULUM KAYNAĞI.
#: (hrma/ içinden depo kökü: bu dosyanın iki üst dizini.)
REQUIREMENTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "requirements.txt")


def install_missing_packages(packages):
    """Install the pinned dependency set from requirements.txt.

    ÖH D18 / altyapi (P10B3-06). ÖLÇÜLDÜ (once_p10b3_14.json): bu fonksiyon
    eksik paketleri TEK TEK ve SÜRÜMSÜZ kuruyordu (``pip install numpy``).
    Deponun kendi requirements.txt'i numpy'yi ``<2`` ile sabitlemişken bu
    yol numpy 2.x indiriyordu; ikili uyumsuzluk (numpy 2 ile derlenmemiş
    scipy/CoolProp/RocketCEA tekerlekleri) uygulamayı içe aktarma anında
    düşürüyor ve kullanıcı bunu "program açılmıyor" diye görüyordu.
    Windows kaynak kurulumunun VARSAYILAN giriş noktası burasıdır
    (start.bat:125-127 bu dosya varsa onu tercih eder), yani kusur
    varsayılan yolda duruyordu.

    Artık kurulum TEK KAYNAKTAN yapılır: requirements.txt. Liste yoksa
    FAIL-CLOSED — sürümsüz kuruluma "yedek" diye düşülmez, çünkü sessizce
    yanlış sürüm kurmak, hiç kurmamaktan kötüdür.
    """
    if not os.path.isfile(REQUIREMENTS):
        print("✗ requirements.txt not found at", REQUIREMENTS)
        print("  Dependencies are only installed from the pinned list;")
        print("  installing unpinned versions would break numpy<2 and the")
        print("  compiled wheels that depend on it.")
        print("  Get a complete source tree, or use the ready-made installer:")
        print("  https://github.com/berketez/HRMA/releases/latest")
        return False
    print("Installing missing packages from pinned requirements.txt:")
    print("  " + ", ".join(packages))
    try:
        # --prefer-binary: pip mümkün olduğunca tekerlek kullansın, kaynaktan
        # derlemeye düşmesin (install.py ile aynı gerekçe).
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--prefer-binary", "-r", REQUIREMENTS,
        ])
        print("✓ dependencies installed from requirements.txt")
    except subprocess.CalledProcessError as e:
        print("✗ Failed to install dependencies from requirements.txt")
        print(f"Error: {e}")
        return False
    return True

def open_browser(port):
    """Open web browser after a delay"""
    time.sleep(2)
    try:
        webbrowser.open(f'http://127.0.0.1:{port}')
        print("✓ Browser opened automatically")
    except Exception as e:
        print(f"! Could not open browser automatically: {e}")
        print(f"Please open http://127.0.0.1:{port} manually")


# ---------------------------------------------------------------------------
# ÖH D17 / altyapi — defter P10B3-05. Buraya kadar bu dosya v2.6.25'te
# `hrma/run.py`de KAPATILAN sabit-8080 kusurunu taşıyordu ve Windows kaynak
# kurulumunun VARSAYILAN giriş noktasıdır (start.bat:125-127 bu dosya varsa
# ONU tercih eder). ÖLÇÜLDÜ (once.json): 8080 sabiti kod satırlarında 11 kez
# geçiyordu, dosyada yedek port arayan tek satır yoktu; 8080'i bir başkası
# tuttuğunda uygulama KAÇMAK yerine "Kill existing process? (y/n)" diye
# soruyor ve onay gelirse `taskkill /PID <pid> /F` ile YABANCI süreci
# öldürüyordu — hangi süreç olduğunu söylemeden.
#
# Port seçimi artık TEK KAYNAKTAN gelir: `hrma.run.pick_port` (PORT_RANGE
# 8080-8090, ilk boş port). Yabancı süreç öldürme yolu KALDIRILDI: kullanıcının
# başka uygulamasını sonlandırmak bir başlatıcının işi değildir. Aralıkta boş
# port yoksa `pick_port` RuntimeError yükseltir ve başlatıcı sayı UYDURMADAN,
# HRMA_PORT'u işaret ederek durur (fail-closed).
# ---------------------------------------------------------------------------
from hrma.run import PORT_RANGE, pick_port          # noqa: E402  (sys.path yukarıda)


def secilen_port():
    """Kullanılacak portu döndürür; HRMA_PORT verilmişse ona uyar.

    `hrma/run.py::run_server` ile AYNI sözleşme — iki giriş noktası bir daha
    ayrışmasın diye port bilgisi tek yerde yaşar.
    """
    zorlanan = os.environ.get('HRMA_PORT')
    if zorlanan:
        return int(zorlanan)
    return pick_port()

def run_server():
    """Run the web server with Windows optimizations"""
    # Add current directory to Python path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Check dependencies
    missing = check_dependencies()
    if missing:
        print("Missing packages detected:")
        for pkg in missing:
            print(f"  - {pkg}")
        print()
        
        if input("Install missing packages? (y/n): ").lower().startswith('y'):
            if not install_missing_packages(missing):
                input("Press Enter to exit...")
                return
        else:
            print("Cannot continue without required packages.")
            input("Press Enter to exit...")
            return
    
    # Port seçimi: yabancı süreç öldürülmez, boş porta KAÇILIR (P10B3-05).
    try:
        port = secilen_port()
    except (RuntimeError, ValueError) as e:
        print(f"✗ {e}")
        print(f"  Scanned ports: {PORT_RANGE.start}-{PORT_RANGE.stop - 1}. "
              "Close one of the applications holding them, or set HRMA_PORT.")
        input("Press Enter to exit...")
        return
    if port != PORT_RANGE.start:
        print(f"! Port {PORT_RANGE.start} is busy — using {port} instead")

    try:
        from hrma.app import app
        # V3 SG-2 / SG-02 (bölüm C): köken kapısına gerçekte bağlanılan port
        # (hrma/run.py ile aynı tek kayıt; start.bat bu dosyayı çalıştırır).
        from hrma.security.origin_gate import register_self_port
        register_self_port(app, port)

        print("=" * 60)
        print("  ROCKET MOTOR ANALYSIS TOOL")
        print(f"  http://127.0.0.1:{port}")
        print("=" * 60)
        print()
        print(f"Platform: {platform.system()} {platform.release()}")
        print("Starting web server...")
        print("Press Ctrl+C to stop")
        print()
        
        # Open browser automatically
        Timer(1.5, open_browser, args=(port,)).start()

        # Use Waitress server for Windows
        try:
            from waitress import serve
            print("Using Waitress server (Windows optimized)")
            print("✓ Server starting...")
            # V3 güvenlik (14 Eki): waitress gövde tavanı = uygulamanın
            # tavanı (tek kaynak body_limit; '+ 1' gerekçesi hrma/run.py
            # waitress dalında: waitress `>=` ile reddeder). Varsayılan
            # 1 GiB, gövde köken kapısından ÖNCE tamponlanıyordu.
            from hrma.security.body_limit import (
                REQUEST_BODY_MAX_BYTES, WAITRESS_CONNECTION_LIMIT)
            serve(app, host='127.0.0.1', port=port, threads=6,
                  connection_limit=WAITRESS_CONNECTION_LIMIT, cleanup_interval=30,
                  max_request_body_size=REQUEST_BODY_MAX_BYTES + 1)
        except ImportError:
            print("Waitress not available, using Flask dev server")
            app.run(host='127.0.0.1', port=port, debug=False,
                    threaded=True, use_reloader=False)
                   
    except ImportError as e:
        print(f"✗ Error importing application modules: {e}")
        print()
        print("This usually means missing dependencies.")
        print("Try running: pip install -r requirements.txt")
        input("Press Enter to exit...")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        input("Press Enter to exit...")

def main():
    """Main function with error handling"""
    clear_screen()
    
    # Check Python version (3.10–3.13 desteklenir, 3.12 önerilir; 3.14+ wheel'siz)
    if sys.version_info < (3, 10):
        print("✗ Python 3.10 or higher is required (3.12 recommended)")
        print(f"Current version: {sys.version}")
        input("Press Enter to exit...")
        return
    if sys.version_info >= (3, 14):
        print("✗ Python 3.14+ is not supported yet (Cantera/CoolProp/RocketCEA lack wheels)")
        print("  Please use Python 3.12.")
        print(f"Current version: {sys.version}")
        input("Press Enter to exit...")
        return
    
    try:
        run_server()
    except KeyboardInterrupt:
        print("\n✓ Server stopped gracefully")
        print("Thank you for using Rocket Motor Analysis Tool!")
        time.sleep(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        input("Press Enter to exit...")

if __name__ == '__main__':
    main()