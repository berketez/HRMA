#!/usr/bin/env python3
"""
macOS Build Script for HRMA Desktop Application
Creates standalone .app bundle using PyInstaller
"""

import os
import sys
import shutil
import subprocess
import plistlib
from pathlib import Path

def build_macos_app():
    """Build macOS .app bundle with PyInstaller"""
    
    print("Building UZAYTEK HRMA for macOS...")
    
    # Get current directory
    current_dir = Path(__file__).parent.absolute()
    os.chdir(current_dir)
    
    # Clean previous builds
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    
    # PyInstaller command for macOS
    pyinstaller_cmd = [
        "pyinstaller",
        "--onedir",                     # Create app bundle
        "--windowed",                   # GUI app (no terminal)
        "--name=UZAYTEK HRMA",         # App name
        "--icon=static/icon.icns",      # App icon (if exists)
        "--add-data=templates:templates",  # Include templates (macOS syntax)
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
        "--osx-bundle-identifier=com.uzaytek.hrma",  # Bundle identifier
        "--clean",                        # Clean PyInstaller cache
        "desktop_app.py"                  # Main script
    ]
    
    try:
        # Run PyInstaller
        print("Running PyInstaller...")
        result = subprocess.run(pyinstaller_cmd, check=True, capture_output=True, text=True)
        print("PyInstaller completed successfully!")
        
        # Check if app bundle was created
        app_path = Path("dist/UZAYTEK HRMA.app")
        if app_path.exists():
            print(f"✓ App bundle created: {app_path.absolute()}")
            
            # Calculate app size
            total_size = sum(f.stat().st_size for f in app_path.rglob('*') if f.is_file())
            print(f"✓ App bundle size: {total_size / (1024*1024):.1f} MB")
            
            # Customize Info.plist
            customize_info_plist(app_path)
            
            # Create DMG distribution package
            create_dmg_package(app_path)
            
        else:
            print("❌ App bundle not found in dist folder")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ PyInstaller failed: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return False
    
    return True

def customize_info_plist(app_path):
    """Customize the Info.plist file for the app bundle"""
    
    info_plist_path = app_path / "Contents" / "Info.plist"
    
    if not info_plist_path.exists():
        print("❌ Info.plist not found")
        return
    
    # Read existing plist
    with open(info_plist_path, 'rb') as f:
        plist_data = plistlib.load(f)
    
    # Update plist with custom information
    plist_data.update({
        'CFBundleDisplayName': 'UZAYTEK HRMA',
        'CFBundleName': 'UZAYTEK HRMA',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'CFBundleIdentifier': 'com.uzaytek.hrma',
        'CFBundleExecutable': 'UZAYTEK HRMA',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': 'UZHR',
        'LSMinimumSystemVersion': '10.15.0',  # macOS Catalina minimum
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'NSHumanReadableCopyright': 'Copyright © 2024 UZAYTEK. All rights reserved.',
        'CFBundleDocumentTypes': [],
        'LSApplicationCategoryType': 'public.app-category.developer-tools',
        'NSAppTransportSecurity': {
            'NSAllowsLocalNetworking': True,
            'NSAllowsArbitraryLoads': True
        }
    })
    
    # Write updated plist
    with open(info_plist_path, 'wb') as f:
        plistlib.dump(plist_data, f)
    
    print("✓ Info.plist customized")

def create_dmg_package(app_path):
    """Create a DMG package for distribution"""
    
    dmg_name = "UZAYTEK_HRMA_Installer.dmg"
    temp_dmg = "temp.dmg"
    
    try:
        # Create temporary DMG
        print("Creating DMG package...")
        
        # Calculate size needed (app size + 50MB buffer)
        app_size = sum(f.stat().st_size for f in app_path.rglob('*') if f.is_file())
        dmg_size = max(100, int((app_size / (1024*1024)) + 50))  # MB
        
        subprocess.run([
            "hdiutil", "create", 
            "-size", f"{dmg_size}m",
            "-fs", "HFS+",
            "-volname", "UZAYTEK HRMA",
            temp_dmg
        ], check=True, capture_output=True)
        
        # Mount the DMG
        mount_result = subprocess.run([
            "hdiutil", "attach", temp_dmg, "-mountpoint", "/tmp/hrma_dmg"
        ], check=True, capture_output=True, text=True)
        
        try:
            # Copy app to DMG
            shutil.copytree(app_path, "/tmp/hrma_dmg/UZAYTEK HRMA.app")
            
            # Create Applications symlink
            os.symlink("/Applications", "/tmp/hrma_dmg/Applications")
            
            # Create README
            readme_content = """UZAYTEK Hybrid Rocket Motor Analysis
====================================

Installation:
1. Drag "UZAYTEK HRMA.app" to the Applications folder
2. Launch from Applications or Spotlight search
3. No additional software required

System Requirements:
- macOS 10.15 (Catalina) or newer
- 4GB RAM minimum
- 500MB free disk space

Usage:
1. Launch the application
2. Click "Launch Application" 
3. The application will open in your default web browser
4. Design and analyze your rocket motors

First Launch:
If you see a security warning, go to:
System Preferences > Security & Privacy > Allow "UZAYTEK HRMA"

Support:
For technical support, contact: berke.tezgocen@uzaytek.com

Version: 1.0
© 2024 UZAYTEK. All rights reserved.
"""
            
            with open("/tmp/hrma_dmg/README.txt", "w") as f:
                f.write(readme_content)
            
            # Set custom icon positions and background (if available)
            create_dmg_appearance_script()
            
        finally:
            # Unmount DMG
            subprocess.run(["hdiutil", "detach", "/tmp/hrma_dmg"], check=True)
        
        # Convert to compressed, read-only DMG
        subprocess.run([
            "hdiutil", "convert", temp_dmg,
            "-format", "UDZO",
            "-o", dmg_name
        ], check=True, capture_output=True)
        
        # Clean up temp DMG
        os.remove(temp_dmg)
        
        dmg_path = Path(dmg_name)
        if dmg_path.exists():
            print(f"✓ DMG package created: {dmg_path.absolute()}")
            print(f"✓ DMG size: {dmg_path.stat().st_size / (1024*1024):.1f} MB")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ DMG creation failed: {e}")
        if os.path.exists(temp_dmg):
            os.remove(temp_dmg)
    except Exception as e:
        print(f"❌ DMG creation error: {e}")

def create_dmg_appearance_script():
    """Create AppleScript to customize DMG appearance"""
    
    applescript = '''
tell application "Finder"
    tell disk "UZAYTEK HRMA"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {400, 100, 900, 450}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 72
        set position of item "UZAYTEK HRMA.app" of container window to {150, 200}
        set position of item "Applications" of container window to {350, 200}
        set position of item "README.txt" of container window to {250, 300}
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
'''
    
    with open("/tmp/hrma_dmg/customize_dmg.applescript", "w") as f:
        f.write(applescript)

def codesign_app(app_path):
    """Code sign the application (requires developer certificate)"""
    
    try:
        # Check if developer certificate is available
        cert_result = subprocess.run([
            "security", "find-identity", "-v", "-p", "codesigning"
        ], capture_output=True, text=True)
        
        if "Developer ID" in cert_result.stdout:
            print("Code signing application...")
            subprocess.run([
                "codesign", "--force", "--verify", "--verbose", "--sign", 
                "Developer ID Application", str(app_path)
            ], check=True)
            print("✓ Application signed")
        else:
            print("⚠️  No developer certificate found - app not signed")
            print("   Users may see security warnings on first launch")
            
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Code signing failed: {e}")
        print("   App will work but may show security warnings")

if __name__ == "__main__":
    print("UZAYTEK HRMA macOS Build Tool")
    print("=" * 40)
    
    # Check if PyInstaller is installed
    try:
        subprocess.run(["pyinstaller", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("✓ PyInstaller installed")
    
    # Build app bundle
    if build_macos_app():
        print("\n✓ macOS build completed successfully!")
        print("\nNext steps:")
        print("1. Test the app: dist/UZAYTEK HRMA.app")
        print("2. Install from DMG: UZAYTEK_HRMA_Installer.dmg")
        print("3. Distribute the DMG file")
        print("\nNote: Users may see security warnings on first launch.")
        print("      To avoid this, the app needs to be notarized by Apple.")
    else:
        print("\n❌ macOS build failed!")
        sys.exit(1)