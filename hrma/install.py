#!/usr/bin/env python3
"""
Cross-platform installer and dependency checker
for UZAYTEK Rocket Motor Analysis

Thin wrapper: checks the Python version, installs the pinned
dependencies from the repository's requirements.txt, then verifies
that the application imports cleanly.
"""

import os
import platform
import subprocess
import sys

# Repo kökü: bu dosya hrma/ altında, bir üst dizin repo köküdür.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(REPO_ROOT, "requirements.txt")


def check_python_version():
    """Check if Python version is adequate (3.10-3.13 supported, 3.12 recommended)"""
    version = sys.version_info
    if version.major != 3 or version.minor < 10:
        print(f"Error: Python {version.major}.{version.minor} detected.")
        print("Python 3.10-3.13 is required (3.12 recommended).")
        return False
    if version.minor >= 14:
        print(f"Error: Python {version.major}.{version.minor} detected.")
        print("Python 3.14+ is not supported yet: compiled dependencies (numpy<2,")
        print("CoolProp, RocketCEA) do not ship 3.14 wheels. Please use Python 3.12.")
        return False
    print(f"OK: Python {version.major}.{version.minor}.{version.micro} detected")
    return True


def install_requirements():
    """Install pinned dependencies from the repository requirements.txt"""
    if not os.path.isfile(REQUIREMENTS):
        print(f"Error: requirements.txt not found at {REQUIREMENTS}")
        return False
    print(f"Installing dependencies from {REQUIREMENTS} ...")
    print("This may take a few minutes on first run...")
    # --prefer-binary: pip mumkun oldugunca wheel kullansin, sdist derlemesin
    # (numpy meson build hatasinin ana sebebi kaynaktan derlemeye dusmesiydi).
    result = subprocess.run([
        sys.executable, "-m", "pip", "install",
        "--prefer-binary", "-r", REQUIREMENTS,
    ])
    if result.returncode != 0:
        print()
        print("Error: Failed to install required packages!")
        print("Common solutions:")
        print("1. Check your internet connection")
        print("2. Use Python 3.12 (3.14+ has no wheels for some packages)")
        print("3. EASIEST: use the ready-made installer instead of source:")
        print("   https://github.com/berketez/HRMA/releases/latest")
        return False
    print("OK: All dependencies installed")
    return True


def verify_app_import():
    """Verify the main application imports cleanly"""
    try:
        sys.path.insert(0, REPO_ROOT)
        from hrma.app import app  # noqa: F401
        print("OK: Application modules loaded successfully")
        return True
    except ImportError as e:
        print(f"Error loading application: {e}")
        return False


def main():
    print("=" * 60)
    print("  UZAYTEK ROCKET MOTOR ANALYSIS")
    print("  Cross-platform Installation Check")
    print("=" * 60)
    print()
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print()

    if not check_python_version():
        input("Press Enter to exit...")
        sys.exit(1)

    if not install_requirements():
        input("Press Enter to exit...")
        sys.exit(1)

    if not verify_app_import():
        input("Press Enter to exit...")
        sys.exit(1)

    print()
    print("Installation complete. You can now run:")
    if platform.system() == "Windows":
        print("  start.bat")
    else:
        print("  ./start.sh")
    print("  or")
    print(f"  {sys.executable} hrma/run.py")
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
