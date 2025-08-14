#!/usr/bin/env python3
"""
Windows Build Script for HRMA Desktop Application
Creates standalone .exe file using PyInstaller
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def build_windows_executable():
    """Build Windows executable with PyInstaller"""
    
    print("Building UZAYTEK HRMA for Windows...")
    
    # Get current directory
    current_dir = Path(__file__).parent.absolute()
    os.chdir(current_dir)
    
    # Clean previous builds
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    
    # PyInstaller command
    pyinstaller_cmd = [
        "pyinstaller",
        "--onefile",                    # Single executable
        "--windowed",                   # No console window
        "--name=UZAYTEK_HRMA",         # Executable name
        "--icon=static/icon.ico",       # Application icon (if exists)
        "--add-data=templates;templates",  # Include templates
        "--add-data=static;static",        # Include static files
        "--add-data=*.py;.",              # Include Python modules
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
        exe_path = Path("dist/UZAYTEK_HRMA.exe")
        if exe_path.exists():
            print(f"✓ Executable created: {exe_path.absolute()}")
            print(f"✓ File size: {exe_path.stat().st_size / (1024*1024):.1f} MB")
            
            # Create distribution folder with all necessary files
            dist_folder = Path("dist/UZAYTEK_HRMA_Distribution")
            dist_folder.mkdir(exist_ok=True)
            
            # Copy executable
            shutil.copy2(exe_path, dist_folder / "UZAYTEK_HRMA.exe")
            
            # Create README for users
            readme_content = """UZAYTEK Hybrid Rocket Motor Analysis
====================================

Installation:
1. Simply double-click UZAYTEK_HRMA.exe to launch
2. No Python installation required
3. The application will start a web server and open in your browser

System Requirements:
- Windows 10 or newer
- 4GB RAM minimum
- 500MB free disk space

Usage:
1. Double-click the executable
2. Click "Launch Application" 
3. The application will open in your default web browser
4. Design and analyze your rocket motors

Support:
For technical support, contact: berke.tezgocen@uzaytek.com

Version: 1.0
Build Date: """ + subprocess.check_output(['date', '/t'], shell=True).decode().strip()
            
            with open(dist_folder / "README.txt", "w") as f:
                f.write(readme_content)
            
            print(f"✓ Distribution package created: {dist_folder.absolute()}")
            
        else:
            print("❌ Executable not found in dist folder")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ PyInstaller failed: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return False
    
    return True

def create_installer_script():
    """Create NSIS installer script for Windows"""
    
    nsis_script = '''
; UZAYTEK HRMA Installer Script
!define APPNAME "UZAYTEK HRMA"
!define COMPANYNAME "UZAYTEK"
!define DESCRIPTION "Hybrid Rocket Motor Analysis Tool"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0

RequestExecutionLevel admin

InstallDir "$PROGRAMFILES\\${COMPANYNAME}\\${APPNAME}"

Name "${APPNAME}"
Icon "static\\icon.ico"
outFile "UZAYTEK_HRMA_Installer.exe"

!include LogicLib.nsh

page components
page directory
page instfiles

!macro VerifyUserIsAdmin
UserInfo::GetAccountType
pop $0
${If} $0 != "admin"
    messageBox mb_iconstop "Administrator rights required!"
    setErrorLevel 740
    quit
${EndIf}
!macroend

function .onInit
    setShellVarContext all
    !insertmacro VerifyUserIsAdmin
functionEnd

section "install"
    setOutPath $INSTDIR
    file "dist\\UZAYTEK_HRMA.exe"
    file "README.txt"
    
    writeUninstaller "$INSTDIR\\uninstall.exe"
    
    createDirectory "$SMPROGRAMS\\${COMPANYNAME}"
    createShortCut "$SMPROGRAMS\\${COMPANYNAME}\\${APPNAME}.lnk" "$INSTDIR\\UZAYTEK_HRMA.exe"
    createShortCut "$DESKTOP\\${APPNAME}.lnk" "$INSTDIR\\UZAYTEK_HRMA.exe"
    
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "UninstallString" "$\\"$INSTDIR\\uninstall.exe$\\""
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "QuietUninstallString" "$\\"$INSTDIR\\uninstall.exe$\\" /S"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "InstallLocation" "$\\"$INSTDIR$\\""
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}" "NoRepair" 1
sectionEnd

section "uninstall"
    delete "$INSTDIR\\UZAYTEK_HRMA.exe"
    delete "$INSTDIR\\README.txt"
    delete "$INSTDIR\\uninstall.exe"
    
    delete "$SMPROGRAMS\\${COMPANYNAME}\\${APPNAME}.lnk"
    delete "$DESKTOP\\${APPNAME}.lnk"
    
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${COMPANYNAME} ${APPNAME}"
    
    rmDir "$INSTDIR"
    rmDir "$SMPROGRAMS\\${COMPANYNAME}"
sectionEnd
'''
    
    with open("installer.nsi", "w") as f:
        f.write(nsis_script)
    
    print("✓ NSIS installer script created: installer.nsi")
    print("  To create installer, run: makensis installer.nsi")

if __name__ == "__main__":
    print("UZAYTEK HRMA Windows Build Tool")
    print("=" * 40)
    
    # Check if PyInstaller is installed
    try:
        subprocess.run(["pyinstaller", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("✓ PyInstaller installed")
    
    # Build executable
    if build_windows_executable():
        print("\n✓ Windows build completed successfully!")
        print("\nNext steps:")
        print("1. Test the executable: dist/UZAYTEK_HRMA.exe")
        print("2. Create installer (optional): makensis installer.nsi")
        print("3. Distribute the files in: dist/UZAYTEK_HRMA_Distribution/")
        
        create_installer_script()
    else:
        print("\n❌ Windows build failed!")
        sys.exit(1)