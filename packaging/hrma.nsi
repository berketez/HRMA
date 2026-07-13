; HRMA Windows kurulum sihirbazı (NSIS / MUI2, İngilizce arayüz)
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define APPNAME "HRMA"
!define APPFULL "HRMA - Hybrid Rocket Motor Analysis"
!define COMPANY "UZAYTEK"
; Sürüm derleme komutundan gelir: makensis -DVERSION=2.3.0 hrma.nsi
; (tek kaynak: hrma/__init__.py — build betiği okuyup geçirir)
!ifndef VERSION
  !define VERSION "0.0.0-dev"
!endif
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\HRMA"

Name "${APPFULL}"
OutFile "HRMA-Setup-${VERSION}.exe"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\HRMA"

!include "MUI2.nsh"

!define MUI_ICON "hrma.ico"
!define MUI_UNICON "hrma.ico"
!define MUI_WELCOMEPAGE_TITLE "Welcome to HRMA Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will install the UZAYTEK Hybrid Rocket Motor Analysis suite on your computer.$\r$\n$\r$\nThe installation uses about 2.5 GB of disk space and does NOT require an internet connection.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "Launch HRMA now"
!define MUI_FINISHPAGE_TITLE "Installation Complete"
!define MUI_FINISHPAGE_TEXT "HRMA has been installed successfully.$\r$\n$\r$\nDouble-click the HRMA icon on your desktop to start it at any time. HRMA opens in its own window; closing the window also closes the program.$\r$\n$\r$\nNote: if HRMA is running while you install an update, close it first."
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Function LaunchApp
  SetOutPath "$INSTDIR\app"
  Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\launcher.py"'
FunctionEnd

Section "HRMA" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "win/payload/python"
  File /r "win/payload/libs"
  File /r "win/payload/app"
  File "hrma.ico"

  ; Kısayollar
  SetOutPath "$INSTDIR\app"
  CreateShortCut "$DESKTOP\HRMA.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "UZAYTEK Hybrid Rocket Motor Analysis"
  CreateDirectory "$SMPROGRAMS\HRMA"
  CreateShortCut "$SMPROGRAMS\HRMA\HRMA.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "UZAYTEK Hybrid Rocket Motor Analysis"

  ; Kaldırıcı + Program Ekle/Kaldır kaydı
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortCut "$SMPROGRAMS\HRMA\Uninstall HRMA.lnk" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APPFULL}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "${COMPANY}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\hrma.ico"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" 2500000
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\HRMA.lnk"
  RMDir /r "$SMPROGRAMS\HRMA"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTKEY}"
SectionEnd
