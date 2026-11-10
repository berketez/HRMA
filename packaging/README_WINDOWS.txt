HRMA — Rocket Motor Analysis (Windows Installation)
===================================================================

INSTALLATION:

1) Double-click the "HRMA-Setup-X.Y.Z.exe" file.

2) If the blue "Windows protected your PC" screen appears:
   - Click "More info"
   - Click "Run anyway"
   (This warning appears because the installer is not digitally
   signed; it is normal.)

3) In the setup wizard: Next → Next → Install → Finish.
   NO internet connection and NO administrator password required.

4) After installation an HRMA icon appears on your desktop.


USAGE:

- Double-click the HRMA icon; the window opens within seconds while
  the computation engines load in the background.
- HRMA opens in its own NATIVE window (Windows WebView2 —
  preinstalled on Windows 10/11; Chrome is NOT required).
- When a new version is released, HRMA asks at startup; one click
  downloads the update and starts the installer.
- Closing the HRMA window also closes the program. Double-click
  the icon to open it again.
- Reports, CAD files and drawings you export are saved through a
  save dialog that starts in your Downloads folder; you choose the
  final location there. Documents\HRMA (menu: Open Output Folder)
  holds your saved projects (Documents\HRMA\projects) and the
  program log (hrma_log.txt).

UNINSTALL:

Settings → Apps → HRMA → Uninstall
(or Start menu → HRMA → Uninstall HRMA)

If you run into problems, open an issue at https://github.com/berketez/HRMA/issues and attach this file:
Documents\HRMA\hrma_log.txt


LICENSE:

HRMA is free software under the GNU General Public License, version 3
or (at your option) any later version. The full licence text and the
third-party licence notices are installed with the program, in the
installation folder (by default %LOCALAPPDATA%\HRMA): app\LICENSE and the
app\licenses folder.
Source code: https://github.com/berketez/HRMA
