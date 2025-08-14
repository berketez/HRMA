#!/usr/bin/env python
"""
Windows-optimized launcher for Hybrid Rocket Motor Analysis Tool
Includes enhanced error handling and Windows-specific optimizations
"""

import os
import sys
import platform
import webbrowser
import time
import subprocess
from threading import Timer

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

def install_missing_packages(packages):
    """Install missing packages"""
    print("Installing missing packages...")
    for package in packages:
        print(f"Installing {package}...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", package
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            print(f"✓ {package} installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install {package}")
            print(f"Error: {e.stderr.decode() if e.stderr else 'Unknown error'}")
            return False
    return True

def open_browser():
    """Open web browser after a delay"""
    time.sleep(2)
    try:
        webbrowser.open('http://localhost:5000')
        print("✓ Browser opened automatically")
    except Exception as e:
        print(f"! Could not open browser automatically: {e}")
        print("Please open http://localhost:5000 manually")

def check_port_availability():
    """Check if port 5000 is available"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', 5000))
            return True
        except OSError:
            return False

def kill_process_on_port(port):
    """Kill process running on specified port (Windows)"""
    try:
        # Find process using the port
        result = subprocess.run([
            'netstat', '-ano'
        ], capture_output=True, text=True, shell=True)
        
        lines = result.stdout.split('\n')
        for line in lines:
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    subprocess.run(['taskkill', '/PID', pid, '/F'], 
                                 capture_output=True, shell=True)
                    print(f"✓ Killed process {pid} on port {port}")
                    return True
    except Exception as e:
        print(f"! Could not kill process on port {port}: {e}")
    return False

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
    
    # Check port availability
    if not check_port_availability():
        print("⚠ Port 5000 is already in use")
        if input("Kill existing process? (y/n): ").lower().startswith('y'):
            if not kill_process_on_port(5000):
                print("Could not free port 5000. Please close other applications.")
                input("Press Enter to exit...")
                return
        else:
            print("Cannot start server on port 5000.")
            input("Press Enter to exit...")
            return
    
    try:
        from app import app
        
        print("=" * 60)
        print("  HYBRID ROCKET MOTOR ANALYSIS TOOL")
        print("  http://localhost:5000")
        print("=" * 60)
        print()
        print(f"Platform: {platform.system()} {platform.release()}")
        print("Starting web server...")
        print("Press Ctrl+C to stop")
        print()
        
        # Open browser automatically
        Timer(1.5, open_browser).start()
        
        # Use Waitress server for Windows
        try:
            from waitress import serve
            print("Using Waitress server (Windows optimized)")
            print("✓ Server starting...")
            serve(app, host='127.0.0.1', port=5000, threads=6, 
                  connection_limit=1000, cleanup_interval=30)
        except ImportError:
            print("Waitress not available, using Flask dev server")
            app.run(host='127.0.0.1', port=5000, debug=False, 
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
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("✗ Python 3.7 or higher is required")
        print(f"Current version: {sys.version}")
        input("Press Enter to exit...")
        return
    
    try:
        run_server()
    except KeyboardInterrupt:
        print("\n✓ Server stopped gracefully")
        print("Thank you for using Hybrid Rocket Motor Analysis Tool!")
        time.sleep(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        input("Press Enter to exit...")

if __name__ == '__main__':
    main()