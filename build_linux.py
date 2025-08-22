#!/usr/bin/env python3
"""
Linux Build Script for HRMA Desktop Application
Creates standalone executable using PyInstaller
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def build_linux_executable():
    """Build Linux executable with PyInstaller"""
    
    print("Building UZAYTEK HRMA for Linux...")
    
    # Get current directory
    current_dir = Path(__file__).parent.absolute()
    os.chdir(current_dir)
    
    # Clean previous builds
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    
    # PyInstaller command for Linux
    pyinstaller_cmd = [
        "pyinstaller",
        "--onefile",                    # Single executable
        "--windowed",                   # GUI app (no terminal)
        "--name=UZAYTEK_HRMA",         # Executable name
        "--add-data=templates:templates",  # Include templates (Linux syntax)
        "--add-data=static:static",        # Include static files
        "--add-data=*.py:.",              # Include Python modules
        "--hidden-import=scipy",          # Include scipy
        "--hidden-import=numpy",          # Include numpy
        "--hidden-import=plotly",         # Include plotly
        "--hidden-import=trimesh",        # Include trimesh
        "--hidden-import=flask",          # Include flask
        "--hidden-import=PIL",            # Include Pillow
        "--hidden-import=tkinter",        # Include tkinter
        "--hidden-import=webbrowser",     # Include webbrowser
        "--hidden-import=threading",      # Include threading
        "--hidden-import=socket",         # Include socket
        "--clean",                        # Clean PyInstaller cache
        "desktop_app.py"                  # Main script
    ]
    
    try:
        # Run PyInstaller
        print("Running PyInstaller...")
        result = subprocess.run(pyinstaller_cmd, check=True, capture_output=True, text=True)
        print("PyInstaller completed successfully!")
        
        # Check if executable was created
        exe_path = Path("dist/UZAYTEK_HRMA")
        if exe_path.exists():
            print(f"Executable created: {exe_path.absolute()}")
            print(f"File size: {exe_path.stat().st_size / (1024*1024):.1f} MB")
            
            # Make executable
            os.chmod(exe_path, 0o755)
            
            # Create distribution package
            create_linux_package(exe_path)
            
        else:
            print("Error: Executable not found in dist folder")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Error: PyInstaller failed: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        print(f"Error: Build failed: {e}")
        return False
    
    return True

def create_linux_package(exe_path):
    """Create Linux distribution package"""
    
    # Create distribution directory
    dist_folder = Path("dist/UZAYTEK_HRMA_Linux")
    dist_folder.mkdir(exist_ok=True)
    
    # Copy executable
    shutil.copy2(exe_path, dist_folder / "UZAYTEK_HRMA")
    
    # Create desktop entry file
    desktop_entry = """[Desktop Entry]
Version=1.0
Name=UZAYTEK HRMA
Comment=Hybrid Rocket Motor Analysis Tool
Exec={}/UZAYTEK_HRMA
Icon={}/icon.png
Terminal=false
Type=Application
Categories=Science;Engineering;Development;
StartupNotify=true
""".format(dist_folder.absolute(), dist_folder.absolute())
    
    with open(dist_folder / "UZAYTEK_HRMA.desktop", "w") as f:
        f.write(desktop_entry)
    
    # Make desktop file executable
    os.chmod(dist_folder / "UZAYTEK_HRMA.desktop", 0o755)
    
    # Create installation script
    install_script = """#!/bin/bash
# UZAYTEK HRMA Installation Script for Linux

echo "UZAYTEK Hybrid Rocket Motor Analysis - Linux Installer"
echo "====================================================="

# Check if running as root for system-wide install
if [ "$EUID" -eq 0 ]; then
    INSTALL_DIR="/opt/uzaytek-hrma"
    DESKTOP_DIR="/usr/share/applications"
    BIN_DIR="/usr/local/bin"
    echo "Installing system-wide..."
else
    INSTALL_DIR="$HOME/.local/share/uzaytek-hrma"
    DESKTOP_DIR="$HOME/.local/share/applications"
    BIN_DIR="$HOME/.local/bin"
    echo "Installing for current user..."
fi

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$BIN_DIR"

# Copy files
echo "Copying files..."
cp UZAYTEK_HRMA "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/UZAYTEK_HRMA"

# Update desktop entry with correct paths
sed "s|{INSTALL_DIR}|$INSTALL_DIR|g" UZAYTEK_HRMA.desktop > "$DESKTOP_DIR/uzaytek-hrma.desktop"

# Create symlink in PATH
ln -sf "$INSTALL_DIR/UZAYTEK_HRMA" "$BIN_DIR/uzaytek-hrma"

echo "Installation completed!"
echo ""
echo "To run the application:"
echo "1. From terminal: uzaytek-hrma"
echo "2. From desktop: Search for 'UZAYTEK HRMA' in applications"
echo "3. Direct path: $INSTALL_DIR/UZAYTEK_HRMA"
echo ""
echo "To uninstall:"
echo "  Run: $INSTALL_DIR/uninstall.sh"
"""
    
    with open(dist_folder / "install.sh", "w") as f:
        f.write(install_script)
    os.chmod(dist_folder / "install.sh", 0o755)
    
    # Create uninstall script
    uninstall_script = """#!/bin/bash
# UZAYTEK HRMA Uninstall Script

echo "Uninstalling UZAYTEK HRMA..."

# Check installation type
if [ -f "/opt/uzaytek-hrma/UZAYTEK_HRMA" ]; then
    # System-wide installation
    sudo rm -rf /opt/uzaytek-hrma
    sudo rm -f /usr/share/applications/uzaytek-hrma.desktop
    sudo rm -f /usr/local/bin/uzaytek-hrma
else
    # User installation
    rm -rf "$HOME/.local/share/uzaytek-hrma"
    rm -f "$HOME/.local/share/applications/uzaytek-hrma.desktop"
    rm -f "$HOME/.local/bin/uzaytek-hrma"
fi

echo "UZAYTEK HRMA has been uninstalled"
"""
    
    with open(dist_folder / "uninstall.sh", "w") as f:
        f.write(uninstall_script)
    os.chmod(dist_folder / "uninstall.sh", 0o755)
    
    # Create README
    readme_content = """UZAYTEK Hybrid Rocket Motor Analysis - Linux
===========================================

System Requirements:
- Linux (Ubuntu 18.04+, CentOS 7+, or equivalent)
- X11 display server
- 4GB RAM minimum
- 500MB free disk space

Installation:
1. Extract this package to any directory
2. Run: ./install.sh
3. Follow the prompts

Usage:
1. Run 'uzaytek-hrma' from terminal, or
2. Find "UZAYTEK HRMA" in your applications menu
3. Click "Launch Application" in the desktop app
4. The application will open in your web browser

Manual Launch:
./UZAYTEK_HRMA

Uninstall:
Run the uninstall script: ./uninstall.sh

Support:
For technical support, contact: berke.tezgocen@uzaytek.com

Version: 1.0
© 2024 UZAYTEK. All rights reserved.
"""
    
    with open(dist_folder / "README.txt", "w") as f:
        f.write(readme_content)
    
    print(f"Linux distribution package created: {dist_folder.absolute()}")

if __name__ == "__main__":
    print("UZAYTEK HRMA Linux Build Tool")
    print("=" * 40)
    
    # Check if PyInstaller is installed
    try:
        subprocess.run(["pyinstaller", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("PyInstaller installed")
    
    # Build executable
    if build_linux_executable():
        print("\nLinux build completed successfully!")
        print("\nNext steps:")
        print("1. Test the executable: dist/UZAYTEK_HRMA")
        print("2. Install: cd dist/UZAYTEK_HRMA_Linux && ./install.sh")
        print("3. Distribute the Linux package folder")
    else:
        print("\nLinux build failed!")
        sys.exit(1)