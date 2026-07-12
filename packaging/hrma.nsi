; HRMA Windows kurulum sihirbazı (NSIS / MUI2, Türkçe)
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define APPNAME "HRMA"
!define APPFULL "HRMA - Hibrit Roket Motor Analizi"
!define COMPANY "UZAYTEK"
!define VERSION "1.0.0"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\HRMA"

Name "${APPFULL}"
OutFile "HRMA-Kurulum-${VERSION}.exe"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\HRMA"

!include "MUI2.nsh"

!define MUI_ICON "hrma.ico"
!define MUI_UNICON "hrma.ico"
!define MUI_WELCOMEPAGE_TITLE "HRMA Kurulumuna Hoş Geldiniz"
!define MUI_WELCOMEPAGE_TEXT "Bu sihirbaz UZAYTEK Hibrit Roket Motor Analizi aracını bilgisayarınıza kuracak.$\r$\n$\r$\nKurulum yaklaşık 2,5 GB disk alanı kullanır ve internet bağlantısı GEREKTİRMEZ.$\r$\n$\r$\nDevam etmek için İleri'ye basın."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "HRMA'yı şimdi başlat"
!define MUI_FINISHPAGE_TITLE "Kurulum Tamamlandı"
!define MUI_FINISHPAGE_TEXT "HRMA başarıyla kuruldu.$\r$\n$\r$\nMasaüstünüzdeki HRMA simgesine çift tıklayarak istediğiniz zaman başlatabilirsiniz. Program açıldığında siyah bir pencere ve ardından tarayıcınızda HRMA arayüzü görünür. Siyah pencereyi kapatmayın, küçültün."
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Turkish"

Function LaunchApp
  SetOutPath "$INSTDIR\app"
  Exec '"$INSTDIR\python\python.exe" "$INSTDIR\app\launcher.py"'
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
  CreateShortCut "$DESKTOP\HRMA.lnk" "$INSTDIR\python\python.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "UZAYTEK Hibrit Roket Motor Analizi"
  CreateDirectory "$SMPROGRAMS\HRMA"
  CreateShortCut "$SMPROGRAMS\HRMA\HRMA.lnk" "$INSTDIR\python\python.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "UZAYTEK Hibrit Roket Motor Analizi"

  ; Kaldırıcı + Program Ekle/Kaldır kaydı
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortCut "$SMPROGRAMS\HRMA\HRMA Kaldir.lnk" "$INSTDIR\uninstall.exe"
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
