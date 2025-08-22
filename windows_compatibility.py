"""
Windows Compatibility and Bug Prevention Module
Handles cross-platform issues and Windows-specific fixes
"""

import os
import sys
import platform
import json
import subprocess
import locale
import warnings
from pathlib import Path
from typing import Dict, Any, Optional

class WindowsCompatibility:
    """Comprehensive Windows compatibility handler"""
    
    def __init__(self):
        self.is_windows = platform.system() == 'Windows'
        self.platform_info = {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'python_version': sys.version,
            'python_implementation': platform.python_implementation()
        }
        
    def setup_windows_environment(self):
        """Configure Windows-specific environment settings"""
        if not self.is_windows:
            return
        
        fixes_applied = []
        
        # 1. Fix encoding issues
        try:
            # Set UTF-8 as default encoding
            if sys.platform == 'win32':
                import codecs
                # Force UTF-8 for stdout/stderr
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
                
                # Set environment variables
                os.environ['PYTHONIOENCODING'] = 'utf-8'
                os.environ['LANG'] = 'en_US.UTF-8'
                
                fixes_applied.append("UTF-8 encoding configured")
        except Exception as e:
            warnings.warn(f"Could not set UTF-8 encoding: {e}")
        
        # 2. Fix path separators
        try:
            # Ensure proper path handling
            os.environ['PATHEXT'] = os.environ.get('PATHEXT', '') + ';.PY;.PYW'
            fixes_applied.append("Path separators configured")
        except Exception as e:
            warnings.warn(f"Path configuration error: {e}")
        
        # 3. Fix Windows file permissions
        try:
            # Ensure temp directory exists and is writable
            temp_dir = Path(os.environ.get('TEMP', '/tmp'))
            app_temp = temp_dir / 'HRMA'
            app_temp.mkdir(exist_ok=True)
            os.environ['HRMA_TEMP'] = str(app_temp)
            fixes_applied.append("Temp directory configured")
        except Exception as e:
            warnings.warn(f"Temp directory error: {e}")
        
        # 4. Fix multiprocessing on Windows
        try:
            if hasattr(sys, 'frozen'):
                # Running as compiled executable
                import multiprocessing
                multiprocessing.freeze_support()
                fixes_applied.append("Multiprocessing freeze support enabled")
        except Exception as e:
            warnings.warn(f"Multiprocessing setup error: {e}")
        
        # 5. Fix DLL loading issues
        try:
            if self.is_windows:
                # Add Python DLL directories
                if hasattr(os, 'add_dll_directory'):
                    # Python 3.8+ on Windows
                    import site
                    for path in site.getsitepackages():
                        dll_path = Path(path) / 'bin'
                        if dll_path.exists():
                            os.add_dll_directory(str(dll_path))
                fixes_applied.append("DLL directories configured")
        except Exception as e:
            warnings.warn(f"DLL configuration error: {e}")
        
        # 6. Fix locale issues
        try:
            # Set locale to handle decimal points correctly
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except:
            try:
                locale.setlocale(locale.LC_ALL, 'C.UTF-8')
            except:
                try:
                    locale.setlocale(locale.LC_ALL, '')
                except:
                    warnings.warn("Could not set locale")
        
        return fixes_applied
    
    def fix_file_paths(self, path: str) -> str:
        """Convert paths to Windows format"""
        if not self.is_windows:
            return path
        
        # Handle various path formats
        if path:
            # Convert forward slashes to backslashes
            path = path.replace('/', '\\')
            
            # Handle UNC paths
            if path.startswith('\\\\'):
                return path
            
            # Handle drive letters
            if len(path) > 1 and path[1] == ':':
                return path
            
            # Convert relative paths to absolute
            try:
                return str(Path(path).resolve())
            except:
                return path
        
        return path
    
    def fix_flask_configuration(self, app):
        """Apply Windows-specific Flask fixes"""
        if not self.is_windows:
            return
        
        # Disable debug mode issues on Windows
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        
        # Fix static file serving
        app.config['PREFERRED_URL_SCHEME'] = 'http'
        
        # Handle Windows file locking
        app.config['SESSION_FILE_MODE'] = 0o600
        
        # Fix JSON encoding
        app.config['JSON_AS_ASCII'] = False
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Threading fixes for Windows
        app.config['THREADED'] = True
        
    def fix_database_paths(self, db_path: str) -> str:
        """Fix database file paths for Windows"""
        if not self.is_windows:
            return db_path
        
        # Convert to absolute path
        db_path = self.fix_file_paths(db_path)
        
        # Ensure parent directory exists
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        return str(db_path)
    
    def fix_subprocess_commands(self, command: list) -> list:
        """Fix subprocess commands for Windows"""
        if not self.is_windows:
            return command
        
        # Handle python commands
        if command and command[0] in ['python', 'python3']:
            command[0] = sys.executable
        
        # Handle shell built-ins
        shell_builtins = ['echo', 'cd', 'dir', 'copy', 'move', 'del']
        if command and command[0].lower() in shell_builtins:
            return ['cmd', '/c'] + command
        
        return command
    
    def get_windows_fixes_report(self) -> Dict[str, Any]:
        """Generate a report of Windows-specific fixes applied"""
        report = {
            'platform': self.platform_info,
            'python_path': sys.executable,
            'working_directory': os.getcwd(),
            'temp_directory': os.environ.get('HRMA_TEMP', ''),
            'encoding': {
                'stdout': sys.stdout.encoding,
                'stderr': sys.stderr.encoding,
                'filesystem': sys.getfilesystemencoding(),
                'default': sys.getdefaultencoding()
            },
            'environment_variables': {
                'PYTHONIOENCODING': os.environ.get('PYTHONIOENCODING', ''),
                'LANG': os.environ.get('LANG', ''),
                'PATH': os.environ.get('PATH', '').split(os.pathsep)[:5]  # First 5 paths
            }
        }
        
        return report
    
    def check_dependencies(self) -> Dict[str, bool]:
        """Check if all required dependencies are properly installed"""
        dependencies = {}
        
        # Check Python packages
        required_packages = [
            'flask', 'numpy', 'scipy', 'matplotlib', 'plotly',
            'pandas', 'trimesh', 'reportlab', 'cantera', 'rocketcea'
        ]
        
        for package in required_packages:
            try:
                __import__(package)
                dependencies[package] = True
            except ImportError:
                dependencies[package] = False
        
        # Check system dependencies on Windows
        if self.is_windows:
            # Check for Visual C++ redistributables
            try:
                import ctypes
                ctypes.cdll.msvcrt
                dependencies['msvcrt'] = True
            except:
                dependencies['msvcrt'] = False
            
            # Check for required DLLs
            required_dlls = ['msvcp140.dll', 'vcruntime140.dll']
            for dll in required_dlls:
                try:
                    ctypes.cdll.LoadLibrary(dll)
                    dependencies[dll] = True
                except:
                    dependencies[dll] = False
        
        return dependencies
    
    def fix_numpy_threading(self):
        """Fix numpy threading issues on Windows"""
        if not self.is_windows:
            return
        
        try:
            # Set threading layers for better Windows compatibility
            os.environ['OMP_NUM_THREADS'] = '1'
            os.environ['MKL_NUM_THREADS'] = '1'
            os.environ['NUMEXPR_NUM_THREADS'] = '1'
            os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
            
            # Import numpy after setting environment variables
            import numpy as np
            np.seterr(all='ignore')  # Suppress warnings that can cause issues
            
        except Exception as e:
            warnings.warn(f"Could not configure numpy threading: {e}")
    
    def create_windows_launcher(self):
        """Create a Windows-specific launcher script"""
        if not self.is_windows:
            return
        
        launcher_content = '''@echo off
title HRMA - Hybrid Rocket Motor Analysis
color 0A

echo ========================================
echo   HRMA - Starting Application
echo ========================================
echo.

REM Set UTF-8 encoding
chcp 65001 > nul

REM Set Python environment
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set FLASK_ENV=production
set FLASK_APP=app.py

REM Check Python installation
python --version > nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

REM Navigate to application directory
cd /d "%~dp0"

REM Check if virtual environment exists
if exist "venv\\Scripts\\activate.bat" (
    echo Activating virtual environment...
    call venv\\Scripts\\activate.bat
) else (
    echo No virtual environment found, using global Python
)

REM Install/upgrade dependencies if needed
echo Checking dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM Clear any temp files
if exist "__pycache__" rd /s /q "__pycache__"
if exist "*.pyc" del /f /q "*.pyc"

REM Start the application
echo.
echo Starting HRMA application...
echo Navigate to http://localhost:5000 in your browser
echo Press Ctrl+C to stop the server
echo.

python app.py

pause
'''
        
        launcher_path = Path('run_windows.bat')
        launcher_path.write_text(launcher_content)
        
        return str(launcher_path)
    
    def create_error_handler(self):
        """Create comprehensive error handler for Windows issues"""
        def handle_windows_error(error):
            error_fixes = {
                'DLL load failed': 'Install Visual C++ Redistributables',
                'No module named': 'Run: pip install -r requirements.txt',
                'Permission denied': 'Run as Administrator or check file permissions',
                'encoding': 'UTF-8 encoding issue - restart with fixed launcher',
                'multiprocessing': 'Add multiprocessing.freeze_support() to main',
                'matplotlib': 'Set matplotlib backend: matplotlib.use("Agg")',
                'file not found': 'Check file paths - use absolute paths on Windows',
                'port already in use': 'Change port or kill existing process',
                'module not found': 'Check PYTHONPATH and virtual environment'
            }
            
            error_str = str(error).lower()
            for key, fix in error_fixes.items():
                if key.lower() in error_str:
                    return f"Windows Error Detected: {error}\nSuggested Fix: {fix}"
            
            return f"Unexpected Error: {error}"
        
        return handle_windows_error

# Global instance
windows_compat = WindowsCompatibility()

def apply_windows_fixes():
    """Apply all Windows compatibility fixes"""
    if platform.system() != 'Windows':
        return None
    
    fixes = windows_compat.setup_windows_environment()
    windows_compat.fix_numpy_threading()
    
    # Create launcher if needed
    launcher = windows_compat.create_windows_launcher()
    
    # Check dependencies
    deps = windows_compat.check_dependencies()
    missing_deps = [k for k, v in deps.items() if not v]
    
    if missing_deps:
        warnings.warn(f"Missing dependencies: {missing_deps}")
    
    return {
        'fixes_applied': fixes,
        'launcher_created': launcher,
        'missing_dependencies': missing_deps,
        'platform_info': windows_compat.platform_info
    }

# Auto-apply fixes on import if on Windows
if platform.system() == 'Windows':
    apply_windows_fixes()