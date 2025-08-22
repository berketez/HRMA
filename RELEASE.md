# UZAYTEK HRMA - Release Documentation

## Download Instructions

### Windows
1. Download `UZAYTEK_HRMA_Windows.zip` from the [Releases](../../releases) page
2. Extract the ZIP file
3. Double-click `UZAYTEK_HRMA.exe` to launch
4. Click "Launch Application" when the desktop app opens
5. The application will open in your web browser

**System Requirements:**
- Windows 10 or newer
- 4GB RAM minimum
- 500MB free disk space
- No Python installation required

### macOS
1. Download `UZAYTEK_HRMA_macOS.zip` from the [Releases](../../releases) page
2. Extract the ZIP file
3. Drag `UZAYTEK HRMA.app` to Applications folder (or double-click to run directly)
4. Launch from Applications or Spotlight search
5. Click "Launch Application" when the desktop app opens
6. The application will open in your web browser

**System Requirements:**
- macOS 10.15 (Catalina) or newer
- 4GB RAM minimum
- 500MB free disk space
- No Python installation required

**First Launch Security:**
If you see a security warning, go to:
System Preferences > Security & Privacy > Allow "UZAYTEK HRMA"

### Linux
1. Download `UZAYTEK_HRMA_Linux.tar.gz` from the [Releases](../../releases) page
2. Extract: `tar -xzf UZAYTEK_HRMA_Linux.tar.gz`
3. Run installation script: `cd UZAYTEK_HRMA_Linux && ./install.sh`
4. Launch from applications menu or run `uzaytek-hrma` in terminal
5. Click "Launch Application" when the desktop app opens
6. The application will open in your web browser

**System Requirements:**
- Linux (Ubuntu 18.04+, CentOS 7+, or equivalent)
- X11 display server
- 4GB RAM minimum
- 500MB free disk space
- No Python installation required

## How It Works

The UZAYTEK HRMA desktop application:

1. **Launches a local web server** on your computer (usually port 5000-5010)
2. **Opens your default browser** to the application URL
3. **Runs completely offline** - no internet connection required for analysis
4. **All data stays local** - nothing is sent to external servers
5. **Self-contained** - includes all required libraries and dependencies

## Features

- **Hybrid Rocket Motor Analysis** - Complete performance calculations
- **STL File Export** - 3D printable motor components
- **Performance Visualization** - Interactive graphs and charts
- **Motor Configuration** - Advanced design parameters
- **Safety Analysis** - Structural and thermal calculations
- **Report Generation** - Professional documentation export

## Troubleshooting

### Windows
- If Windows Defender blocks the file, click "More info" then "Run anyway"
- Make sure you're running Windows 10 or newer
- Try running as administrator if needed

### macOS
- If you get "App can't be opened because it is from an unidentified developer":
  - Right-click the app and select "Open"
  - Or go to System Preferences > Security & Privacy and allow the app
- Make sure you're running macOS 10.15 or newer

### Linux
- If the application doesn't start, try running from terminal to see error messages
- Make sure you have X11 display server running
- Install missing system packages if prompted

### Common Issues
- **Port already in use**: The app will automatically find another available port
- **Browser doesn't open**: Copy the URL from the desktop app window and paste it manually
- **Application freezes**: Restart the desktop application

## Building from Source

If you want to build the executables yourself:

```bash
# Windows
python build_windows.py

# macOS
python build_macos.py

# Linux
python build_linux.py
```

Requirements:
- Python 3.8+
- PyInstaller
- All project dependencies

## Support

For technical support:
- Email: berke.tezgocen@uzaytek.com
- Create an issue in this repository
- Check the documentation in the `docs/` folder

## Version History

### v1.0.0
- Initial release
- Complete hybrid rocket motor analysis
- Cross-platform desktop applications
- STL export functionality
- Performance visualization
- Safety analysis integration

---

© 2024 UZAYTEK. All rights reserved.