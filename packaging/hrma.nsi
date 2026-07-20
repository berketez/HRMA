; HRMA Windows kurulum sihirbazı (NSIS / MUI2, İngilizce arayüz)
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define APPNAME "HRMA"
!define APPFULL "HRMA - Rocket Motor Analysis"
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
!define MUI_WELCOMEPAGE_TEXT "This wizard will install the UZAYTEK Rocket Motor Analysis suite on your computer.$\r$\n$\r$\nThe installation uses about 2.5 GB of disk space and does NOT require an internet connection.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "Launch HRMA now"
!define MUI_FINISHPAGE_TITLE "Installation Complete"
!define MUI_FINISHPAGE_TEXT "HRMA has been installed successfully.$\r$\n$\r$\nDouble-click the HRMA icon on your desktop to start it at any time. HRMA opens in its own window; closing the window also closes the program."
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Function LaunchApp
  SetOutPath "$INSTDIR\app"
  Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\launcher.py"'
FunctionEnd

; --- Çalışan HRMA'yı kapat ---
; 2026-07-20 saha hatası: uygulama içi güncelleyici Setup'ı HRMA hâlâ
; açıkken başlatıyor (update_checker._open_installer). Kilitli dosyalar
; (ör. python\_decimal.pyd) "Error opening file for writing" ile kurulumu
; düşürüyordu. Çözüm: kurulum/kaldırma başında $INSTDIR altından çalışan
; TÜM süreçler (pythonw.exe, python.exe, asılı kaleido.exe) tespit edilir;
; etkileşimli modda kullanıcı onayıyla, sessiz modda (/S) doğrudan
; kapatılır. Süreç tespiti başarısız olursa (PowerShell yok vb.) eski
; davranışa düşülür — kurulum engellenmez.
; NOT: makro iki kez örneklenir; ${un} fonksiyon adı öneki ("un."),
; ${lbl} etiket öneki (nokta içeremez).
; NOT: Get-Process DEĞİL Get-CimInstance kullanılır (2026-07-20 inceleme
; bulgusu, kritik): 32-bit kurucu 32-bit PowerShell başlatır ve 32-bit
; PS'den 64-bit süreçlerin .Path'i $null döner — filtre hiç eşleşmezdi.
; Win32_Process.ExecutablePath bitness'ten bağımsızdır ve NSIS
; kaldırıcısının %TEMP% kopyasını da doğal olarak dışlar.
; NOT: "çalışıyor" sinyali exit 23'tür (1 değil) — PowerShell'in kendi
; hataları exit 1 ürettiğinden 1 kullanmak her PS hatasını sahte
; "HRMA çalışıyor" uyarısına çevirirdi. /TIMEOUT: PS asılırsa Setup
; asılmasın ("timeout"/"error" dönüşü 23 ile eşleşmez → eski davranış).
!macro CLOSE_RUNNING_HRMA un lbl
Function ${un}CloseRunningHRMA
  nsExec::ExecToStack /TIMEOUT=15000 `powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $$_.ExecutablePath -like '$INSTDIR\*' }) { exit 23 } else { exit 0 }"`
  Pop $0
  Pop $1
  StrCmp $0 "23" 0 ${lbl}_no_running
  IfSilent ${lbl}_do_kill
  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "HRMA is currently running and must be closed before setup can continue.$\r$\n$\r$\nClick OK to close HRMA automatically, or Cancel to abort." IDOK ${lbl}_do_kill
  Abort
${lbl}_do_kill:
  ; Stop-Process sonlanmayı BEKLEMEZ — Wait-Process ile 10 sn'ye kadar
  ; beklenir, ardından dosya tanıtıcılarının bırakılması için kısa pay.
  nsExec::ExecToStack /TIMEOUT=25000 `powershell -NoProfile -Command "$$p = Get-CimInstance Win32_Process | Where-Object { $$_.ExecutablePath -like '$INSTDIR\*' }; $$p | ForEach-Object { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue }; $$p | ForEach-Object { Wait-Process -Id $$_.ProcessId -Timeout 10 -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500"`
  Pop $0
  Pop $1
${lbl}_no_running:
FunctionEnd
!macroend

!insertmacro CLOSE_RUNNING_HRMA "" "inst"
!insertmacro CLOSE_RUNNING_HRMA "un." "uninst"

Section "HRMA" SecMain
  SectionIn RO

  ; HRMA açıkken güncelleme: önce çalışan süreçleri kapat (yukarıya bak)
  Call CloseRunningHRMA

  ; --- Temiz güncelleme ---
  ; Aynı dizine kuruluyken eski sürümden artık dosyalar (yeni sürümde
  ; kaldırılmış modüller/kütüphaneler) kalmasın diye program dosyalarını
  ; önce sil, sonra yeniden yaz. Kullanıcı çıktıları Belgeler\HRMA'da
  ; tutulduğu için ($INSTDIR'da DEĞİL) bu silme veriyi etkilemez.
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\libs"
  RMDir /r "$INSTDIR\python"

  SetOutPath "$INSTDIR"
  File /r "win/payload/python"
  File /r "win/payload/libs"
  File /r "win/payload/app"
  File "hrma.ico"

  ; Kısayollar
  SetOutPath "$INSTDIR\app"
  CreateShortCut "$DESKTOP\HRMA.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "UZAYTEK Rocket Motor Analysis"
  CreateDirectory "$SMPROGRAMS\HRMA"
  CreateShortCut "$SMPROGRAMS\HRMA\HRMA.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "UZAYTEK Rocket Motor Analysis"

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
  ; HRMA açıkken kaldırma da aynı kilit sorununu yaşar
  Call un.CloseRunningHRMA
  Delete "$DESKTOP\HRMA.lnk"
  RMDir /r "$SMPROGRAMS\HRMA"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTKEY}"
SectionEnd
