#!/usr/bin/env python3
"""
Hybrid Rocket Motor Analysis Web Application
Cross-platform launcher script (Windows/Mac/Linux)
"""

import os
import sys
import platform
import webbrowser
import time
from threading import Timer

# Betik hrma/ içinde yaşıyor: 'import hrma' için depo kökü sys.path'e eklenir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def open_browser():
    """Open web browser after a delay"""
    time.sleep(1.5)
    try:
        webbrowser.open('http://localhost:8080')
    except:
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

    print("=" * 60)
    print("  HYBRID ROCKET MOTOR ANALYSIS WEB TOOL")
    print("  http://localhost:8080")
    print("=" * 60)
    print()
    print(f"Platform: {platform.system()} {platform.release()}")
    print("Starting web server...")
    print("Press Ctrl+C to stop")
    print()
    
    # Open browser automatically
    Timer(1.0, open_browser).start()
    
    # Use appropriate server for platform
    if platform.system() == "Windows":
        try:
            from waitress import serve
            print("Using Waitress server (Windows optimized)")
            serve(app, host='127.0.0.1', port=8080, threads=4)
        except ImportError:
            print("Waitress not available, using Flask dev server")
            app.run(host='127.0.0.1', port=8080, debug=False, threaded=True, use_reloader=False)
    else:
        # Unix-like systems (Mac/Linux)
        try:
            from gunicorn.app.wsgiapp import WSGIApplication
            print("Using Gunicorn server (Unix optimized)")
            # Note: Gunicorn setup would go here, but Flask dev server is simpler for this use case
            app.run(host='127.0.0.1', port=8080, debug=True, threaded=True, use_reloader=False)
        except ImportError:
            print("Using Flask dev server")
            app.run(host='127.0.0.1', port=8080, debug=True, threaded=True, use_reloader=False)

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