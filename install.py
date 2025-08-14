#!/usr/bin/env python3
"""
Cross-platform installer and dependency checker
for Hybrid Rocket Motor Analysis Tool
"""

import sys
import os
import platform
import subprocess
import importlib.util

def check_python_version():
    """Check if Python version is adequate"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        print(f"Error: Python {version.major}.{version.minor} detected.")
        print("Python 3.7 or higher is required.")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro} detected")
    return True

def check_pip():
    """Check if pip is available"""
    try:
        import pip
        print("✓ pip is available")
        return True
    except ImportError:
        print("! pip is not available")
        return False

def install_package(package_name):
    """Install a package using pip"""
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", package_name
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def check_package(package_name):
    """Check if a package is installed"""
    spec = importlib.util.find_spec(package_name)
    return spec is not None

def main():
    print("=" * 60)
    print("  HYBRID ROCKET MOTOR ANALYSIS TOOL")
    print("  Cross-platform Installation Check")
    print("=" * 60)
    print()
    
    # System info
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print()
    
    # Check Python version
    if not check_python_version():
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Check pip
    if not check_pip():
        print("Installing pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
            print("✓ pip installed successfully")
        except subprocess.CalledProcessError:
            print("✗ Failed to install pip")
            input("Press Enter to exit...")
            sys.exit(1)
    
    # Required packages
    packages = [
        ("flask", "Flask"),
        ("flask_cors", "Flask-CORS"),
        ("numpy", "NumPy"),
        ("scipy", "SciPy"),
        ("plotly", "Plotly"),
        ("pandas", "Pandas")
    ]
    
    # Platform-specific server
    if platform.system() == "Windows":
        packages.append(("waitress", "Waitress"))
    else:
        packages.append(("gunicorn", "Gunicorn"))
    
    print("Checking required packages...")
    print()
    
    missing_packages = []
    
    for import_name, display_name in packages:
        if check_package(import_name):
            print(f"✓ {display_name}")
        else:
            print(f"✗ {display_name} (missing)")
            missing_packages.append(import_name)
    
    print()
    
    if missing_packages:
        print(f"Installing {len(missing_packages)} missing packages...")
        print("This may take a few minutes...")
        print()
        
        failed_packages = []
        
        for package in missing_packages:
            print(f"Installing {package}...", end=" ")
            if install_package(package):
                print("✓")
            else:
                print("✗")
                failed_packages.append(package)
        
        if failed_packages:
            print()
            print("Failed to install the following packages:")
            for package in failed_packages:
                print(f"  - {package}")
            print()
            print("Try installing manually:")
            print(f"  {sys.executable} -m pip install {' '.join(failed_packages)}")
            print()
            input("Press Enter to exit...")
            sys.exit(1)
    
    print()
    print("✓ All dependencies are installed!")
    print()
    print("Installation complete. You can now run:")
    
    if platform.system() == "Windows":
        print("  start.bat")
    else:
        print("  ./start.sh")
    
    print("  or")
    print(f"  {sys.executable} run.py")
    print()
    
    # Test import of main app
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import app
        print("✓ Application modules loaded successfully")
    except ImportError as e:
        print(f"✗ Error loading application: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    print()
    print("Ready to launch!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInstallation cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        input("Press Enter to exit...")
        sys.exit(1)