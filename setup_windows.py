"""
Windows Setup and Installation Script for HRMA
Handles all Windows-specific installation and configuration
"""

import os
import sys
import platform
import subprocess
import json
import shutil
from pathlib import Path
import ctypes
import winreg
import warnings

def is_admin():
    """Check if running with administrator privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with administrator privileges"""
    if is_admin():
        return True
    else:
        # Re-run the program with admin rights
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        return False

class WindowsSetup:
    """Complete Windows setup and configuration for HRMA"""
    
    def __init__(self):
        self.app_dir = Path.cwd()
        self.python_exe = sys.executable
        self.venv_path = self.app_dir / 'venv'
        self.errors = []
        self.warnings = []
        
    def check_python_version(self):
        """Verify Python version compatibility"""
        print("Checking Python version...")
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.errors.append(f"Python 3.8 or higher required. Found: {sys.version}")
            return False
        print(f"✓ Python {version.major}.{version.minor}.{version.micro} detected")
        return True
    
    def install_visual_cpp_check(self):
        """Check for Visual C++ Redistributables"""
        print("\nChecking Visual C++ Redistributables...")
        
        # Check registry for VC++ installations
        vc_versions = {
            '2015-2022': r'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
            '2013': r'SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x64',
            '2012': r'SOFTWARE\Microsoft\VisualStudio\11.0\VC\Runtimes\x64'
        }
        
        installed = False
        for version, key_path in vc_versions.items():
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    installed = True
                    print(f"✓ Visual C++ {version} Redistributable installed")
                    break
            except:
                continue
        
        if not installed:
            self.warnings.append(
                "Visual C++ Redistributables not found. "
                "Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe"
            )
            print("⚠ Visual C++ Redistributables not found")
        
        return installed
    
    def create_virtual_environment(self):
        """Create and setup virtual environment"""
        print("\nSetting up virtual environment...")
        
        if self.venv_path.exists():
            print("Virtual environment already exists")
            return True
        
        try:
            subprocess.run([self.python_exe, '-m', 'venv', str(self.venv_path)], 
                         check=True, capture_output=True)
            print("✓ Virtual environment created")
            return True
        except subprocess.CalledProcessError as e:
            self.errors.append(f"Failed to create virtual environment: {e}")
            return False
    
    def install_dependencies(self):
        """Install all required Python packages"""
        print("\nInstalling dependencies...")
        
        # Determine pip executable
        if self.venv_path.exists():
            pip_exe = self.venv_path / 'Scripts' / 'pip.exe'
        else:
            pip_exe = 'pip'
        
        # Upgrade pip first
        try:
            subprocess.run([str(pip_exe), 'install', '--upgrade', 'pip'], 
                         capture_output=True, check=True)
            print("✓ pip upgraded")
        except:
            self.warnings.append("Could not upgrade pip")
        
        # Core dependencies that must be installed in order
        core_deps = [
            'wheel',
            'setuptools',
            'numpy',
            'scipy',
            'matplotlib',
            'flask',
            'flask-cors'
        ]
        
        for dep in core_deps:
            try:
                subprocess.run([str(pip_exe), 'install', dep], 
                             capture_output=True, check=True)
                print(f"✓ {dep} installed")
            except subprocess.CalledProcessError:
                self.errors.append(f"Failed to install {dep}")
        
        # Install from requirements.txt if it exists
        req_file = self.app_dir / 'requirements.txt'
        if req_file.exists():
            try:
                subprocess.run([str(pip_exe), 'install', '-r', str(req_file)], 
                             capture_output=True, check=True)
                print("✓ All requirements installed")
            except subprocess.CalledProcessError as e:
                self.warnings.append("Some packages from requirements.txt failed to install")
        
        return len(self.errors) == 0
    
    def configure_firewall(self):
        """Configure Windows Firewall for Flask"""
        print("\nConfiguring Windows Firewall...")
        
        if not is_admin():
            self.warnings.append("Run as administrator to configure firewall")
            return False
        
        try:
            # Add firewall rule for Flask
            rule_name = "HRMA Flask Server"
            subprocess.run([
                'netsh', 'advfirewall', 'firewall', 'add', 'rule',
                f'name={rule_name}',
                'dir=in', 'action=allow', 'protocol=TCP',
                'localport=5000'
            ], capture_output=True, check=True)
            print("✓ Firewall rule added for port 5000")
            return True
        except:
            self.warnings.append("Could not configure firewall automatically")
            return False
    
    def create_shortcuts(self):
        """Create desktop and start menu shortcuts"""
        print("\nCreating shortcuts...")
        
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            
            # Desktop shortcut
            desktop = Path.home() / 'Desktop'
            shortcut_path = desktop / 'HRMA.lnk'
            
            shortcut = shell.CreateShortCut(str(shortcut_path))
            shortcut.Targetpath = str(self.app_dir / 'run_windows.bat')
            shortcut.WorkingDirectory = str(self.app_dir)
            shortcut.IconLocation = str(self.app_dir / 'icon.ico') if (self.app_dir / 'icon.ico').exists() else ''
            shortcut.Description = "Hybrid Rocket Motor Analysis"
            shortcut.save()
            
            print("✓ Desktop shortcut created")
            return True
        except:
            self.warnings.append("Could not create shortcuts (win32com not installed)")
            return False
    
    def create_batch_launcher(self):
        """Create optimized batch file launcher"""
        print("\nCreating launcher script...")
        
        launcher_content = f'''@echo off
title HRMA - Hybrid Rocket Motor Analysis
color 0A
cls

echo ==========================================
echo    HRMA - Hybrid Rocket Motor Analysis
echo ==========================================
echo.

REM Set UTF-8 encoding
chcp 65001 > nul 2>&1

REM Set environment variables
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set FLASK_ENV=production
set FLASK_APP=app.py
set WERKZEUG_RUN_MAIN=true

REM Suppress warnings
set PYTHONWARNINGS=ignore

REM Navigate to application directory
cd /d "{self.app_dir}"

REM Activate virtual environment if exists
if exist "venv\\Scripts\\activate.bat" (
    call venv\\Scripts\\activate.bat
) else (
    echo Using system Python installation
)

REM Clear temp files
if exist "__pycache__" rd /s /q "__pycache__" > nul 2>&1
if exist "*.pyc" del /f /q "*.pyc" > nul 2>&1

REM Check if port 5000 is available
netstat -an | findstr :5000 > nul
if not errorlevel 1 (
    echo.
    echo WARNING: Port 5000 is already in use!
    echo Trying alternative port 5001...
    set FLASK_RUN_PORT=5001
    set PORT_NUM=5001
) else (
    set PORT_NUM=5000
)

REM Start application
echo.
echo Starting HRMA application on port %PORT_NUM%...
echo.
echo ==========================================
echo   Open your browser and navigate to:
echo   http://localhost:%PORT_NUM%
echo ==========================================
echo.
echo Press Ctrl+C to stop the server
echo.

REM Run with proper error handling
python app.py 2>&1

if errorlevel 1 (
    echo.
    echo ==========================================
    echo   ERROR: Application failed to start
    echo ==========================================
    echo.
    echo Possible solutions:
    echo 1. Install Python 3.8 or higher
    echo 2. Run: pip install -r requirements.txt
    echo 3. Install Visual C++ Redistributables
    echo 4. Check firewall settings
    echo.
    pause
)

pause
'''
        
        launcher_path = self.app_dir / 'run_windows.bat'
        launcher_path.write_text(launcher_content)
        print("✓ Launcher script created: run_windows.bat")
        return True
    
    def create_config_file(self):
        """Create Windows-specific configuration file"""
        print("\nCreating configuration file...")
        
        config = {
            'platform': 'windows',
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}",
            'app_directory': str(self.app_dir),
            'venv_path': str(self.venv_path) if self.venv_path.exists() else None,
            'settings': {
                'host': '0.0.0.0',
                'port': 5000,
                'debug': False,
                'threaded': True,
                'encoding': 'utf-8'
            },
            'fixes_applied': [
                'utf8_encoding',
                'path_separators',
                'numpy_threading',
                'matplotlib_backend'
            ]
        }
        
        config_path = self.app_dir / 'windows_config.json'
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print("✓ Configuration file created")
        return True
    
    def test_installation(self):
        """Test if the installation works"""
        print("\nTesting installation...")
        
        test_script = '''
import sys
import os
os.environ['TESTING'] = '1'

try:
    from flask import Flask
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    
    print("✓ Core modules imported successfully")
    
    # Test Flask app
    from app import app
    print("✓ Flask app loaded successfully")
    
    # Test calculations
    from hybrid_rocket_engine import HybridRocketEngine
    print("✓ Calculation modules loaded successfully")
    
    print("\\n✅ All tests passed!")
    sys.exit(0)
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
'''
        
        test_file = self.app_dir / 'test_install.py'
        test_file.write_text(test_script)
        
        try:
            # Use venv Python if available
            if self.venv_path.exists():
                python_exe = self.venv_path / 'Scripts' / 'python.exe'
            else:
                python_exe = self.python_exe
            
            result = subprocess.run([str(python_exe), str(test_file)], 
                                  capture_output=True, text=True)
            
            print(result.stdout)
            
            if result.returncode == 0:
                print("✓ Installation test passed")
                test_file.unlink()  # Clean up test file
                return True
            else:
                print("✗ Installation test failed")
                print(result.stderr)
                return False
                
        except Exception as e:
            print(f"✗ Test failed: {e}")
            return False
        finally:
            if test_file.exists():
                test_file.unlink()
    
    def run_setup(self):
        """Run complete Windows setup"""
        print("=" * 50)
        print("HRMA Windows Setup")
        print("=" * 50)
        
        # Check admin rights for full setup
        if not is_admin():
            print("\n⚠ Running without administrator privileges")
            print("Some features may not be configured")
            response = input("\nContinue anyway? (y/n): ")
            if response.lower() != 'y':
                print("\nRestarting with administrator privileges...")
                run_as_admin()
                return
        
        # Run setup steps
        steps = [
            ("Python Version", self.check_python_version),
            ("Visual C++", self.install_visual_cpp_check),
            ("Virtual Environment", self.create_virtual_environment),
            ("Dependencies", self.install_dependencies),
            ("Firewall", self.configure_firewall),
            ("Launcher", self.create_batch_launcher),
            ("Configuration", self.create_config_file),
            ("Shortcuts", self.create_shortcuts),
            ("Installation Test", self.test_installation)
        ]
        
        for step_name, step_func in steps:
            print(f"\n{step_name}...")
            try:
                step_func()
            except Exception as e:
                self.errors.append(f"{step_name} failed: {e}")
        
        # Summary
        print("\n" + "=" * 50)
        print("Setup Complete")
        print("=" * 50)
        
        if self.errors:
            print("\n❌ Errors encountered:")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.warnings:
            print("\n⚠ Warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if not self.errors:
            print("\n✅ Setup completed successfully!")
            print("\nTo start HRMA:")
            print("  1. Double-click 'run_windows.bat'")
            print("  2. Or run: python app.py")
            print("\nThe application will open at http://localhost:5000")
        else:
            print("\n❌ Setup completed with errors")
            print("Please fix the errors and run setup again")
        
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    if platform.system() != 'Windows':
        print("This setup script is for Windows only")
        sys.exit(1)
    
    setup = WindowsSetup()
    setup.run_setup()