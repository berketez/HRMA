; HRMA Windows kurulum sihirbazı (NSIS / MUI2, İngilizce arayüz)
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define APPNAME "HRMA"
!define APPFULL "HRMA - Rocket Motor Analysis"
!define COMPANY "Berke Tezgöçen"
; Sürüm derleme komutundan gelir: makensis -DVERSION=2.3.0 hrma.nsi
; (tek kaynak: hrma/__init__.py — build betiği okuyup geçirir)
!ifndef VERSION
  !define VERSION "0.0.0-dev"
!endif
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\HRMA"

; --- Çıktı dizini -----------------------------------------------------------
; 2026-08-03: OutFile göreli ve dizinsizdi ("HRMA-Setup-x.y.z.exe"), yani exe
; makensis'in çalışma dizinine (pratikte packaging/) düşüyordu. Oysa yayın
; kapısı da (packaging/release_gate.sh) yükleme betiği de (publish_release.sh)
; exe'yi depo kökündeki dist/ altında arıyor — her yayında dosya elle
; taşınıyordu ve taşımayı unutan "artefakt yok" hatası alıyordu.
;
; Yol ${__FILEDIR__} (bu .nsi dosyasının dizini) üzerinden kurulur: böylece
; makensis ister packaging/ içinden ister depo kökünden çağrılsın exe hep
; aynı yere düşer. Ayraç olarak '/' kullanılır; hem POSIX makensis hem de
; Windows dosya API'si kabul eder.
!ifndef OUTDIR
  !define OUTDIR "${__FILEDIR__}/../dist"
!endif
; dist/ yoksa NSIS "can't open output file" ile düşer — derleme zamanında
; oluştur. Windows'ta cmd ayraç olarak '\' ister, bu yüzden ayrı bir kopya
; hazırlanır. Dönüş değeri BİLEREK karşılaştırılmıyor: dizin zaten varsa
; mkdir sıfırdan farklı döner ve bu bir hata değildir.
!ifdef NSIS_WIN32_MAKENSIS
  !searchreplace OUTDIR_YEREL "${OUTDIR}" "/" "\"
  !system 'if not exist "${OUTDIR_YEREL}" mkdir "${OUTDIR_YEREL}"'
!else
  !system 'mkdir -p "${OUTDIR}"'
!endif

Name "${APPFULL}"
OutFile "${OUTDIR}/HRMA-Setup-${VERSION}.exe"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\HRMA"

!include "MUI2.nsh"

!define MUI_ICON "hrma.ico"
!define MUI_UNICON "hrma.ico"
!define MUI_WELCOMEPAGE_TITLE "Welcome to HRMA Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will install the HRMA Rocket Motor Analysis suite on your computer.$\r$\n$\r$\nThe installation uses about 2.5 GB of disk space and does NOT require an internet connection.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME

; ---------------------------------------------------------------------------
; ÖH D17 / altyapi — defter P10B3-23: SEÇİLEN DİZİN DOĞRULANIR.
;
; Buraya kadar kurucu kullanıcıya "Browse" ile herhangi bir dizini seçtiriyor
; ama seçilen dizini HİÇ doğrulamıyordu (ölçüldü: `.onVerifyInstDir`,
; `MUI_DIRECTORYPAGE_*` grep isabeti 0). Sonuç iki geri dönüşsüz silme:
;   * kurulum : RMDir /r "$INSTDIR\app|libs|python"  -> D:\Projeler seçilirse
;               oradaki app\, libs\, python\ klasörleri uyarısız silinirdi
;   * kaldırma: RMDir /r "$INSTDIR"                  -> D:\Projeler'in TAMAMI
; Betiğin kendi gerekçesi ("kullanıcı çıktıları Belgeler\HRMA'da") yalnız
; VARSAYILAN dizin için geçerliydi; dizin sayfası açıkken varsayım
; kullanıcının elindeydi.
;
; Kural: hedef dizin ya YOK/BOŞ olmalı ya da bizim kurulum imzamızı
; (${HRMA_IMZA}) taşımalı. Aksi hâlde İleri düğmesi kapanır — sayı ya da
; klasör UYDURULMAZ, kullanıcıdan başka bir dizin istenir (fail-closed).
; ---------------------------------------------------------------------------
!define HRMA_IMZA "hrma_kurulum.txt"
!define MUI_DIRECTORYPAGE_TEXT_TOP "Choose a folder for HRMA. The folder must be empty or contain a previous HRMA installation; Setup will not overwrite an unrelated folder."
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "Launch HRMA now"
!define MUI_FINISHPAGE_TITLE "Installation Complete"
!define MUI_FINISHPAGE_TEXT "HRMA has been installed successfully.$\r$\n$\r$\nDouble-click the HRMA icon on your desktop to start it at any time. HRMA opens in its own window; closing the window also closes the program."
!insertmacro MUI_PAGE_FINISH

; --- Dizin doğrulaması (P10B3-23) -----------------------------------------
; $R0 = "1" -> dizin YOK ya da BOŞ; "0" -> içinde bizim olmayan şeyler var.
Function HrmaDizinKullanilabilirMi
  Push $R1
  Push $R2
  StrCpy $R0 "1"
  IfFileExists "$INSTDIR\*.*" 0 bitti          ; dizin yok -> kullanılabilir
  IfFileExists "$INSTDIR\${HRMA_IMZA}" bitti 0 ; bizim kurulum -> kullanılabilir
  ; ÖH D19 / altyapi: imza dosyası v2.6.27 ile geldi. Daha ESKİ bir HRMA
  ; kurulumunun üstüne yükseltme yapılırken imza YOKTUR; dizin "yabancı"
  ; sayılırsa yükseltme durur. `uninstall.exe` VE `hrma.ico` birlikte varsa
  ; dizin bizimdir (ikisi birden aranır; tek başına hiçbiri yeterli değil).
  IfFileExists "$INSTDIR\uninstall.exe" 0 tarama
  IfFileExists "$INSTDIR\hrma.ico" bitti 0
  tarama:
  FindFirst $R1 $R2 "$INSTDIR\*.*"
  dongu:
    StrCmp $R2 "" kapat
    StrCmp $R2 "." sonraki
    StrCmp $R2 ".." sonraki
    StrCpy $R0 "0"                              ; yabancı içerik bulundu
    Goto kapat
  sonraki:
    FindNext $R1 $R2
    Goto dongu
  kapat:
  FindClose $R1
  bitti:
  Pop $R2
  Pop $R1
FunctionEnd

Function .onVerifyInstDir
  Push $R0
  Call HrmaDizinKullanilabilirMi
  StrCmp $R0 "1" tamam
  Pop $R0
  Abort                                          ; İleri kapalı kalır
  tamam:
  Pop $R0
FunctionEnd


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

  ; --- ÖH D19 / altyapi — Fable-D17 P10B3-23 ŞARTI (2) ----------------------
  ; `.onVerifyInstDir` YALNIZ dizin sayfası görüldüğünde çağrılır; sessiz
  ; kurulumda (`hrma.exe /S /D=D:\Projeler`) o sayfa hiç açılmaz. Aşağıdaki üç
  ; KOŞULSUZ `RMDir /r` ise $INSTDIR\app, \libs, \python ağaçlarını siler —
  ; yani onarımın kendi gerekçesindeki "D:\Projeler seçilirse uyarısız silinir"
  ; vakası sessiz modda AÇIK kalıyordu (Fable-D17 ölçümü). Doğrulama artık
  ; SİLMEDEN ÖNCE burada da koşar; hüküm kazanılmazsa kurulum DURUR — sessiz
  ; modda da (MessageBox /SD IDOK) ve dizine dokunulmaz.
  Push $R0
  Call HrmaDizinKullanilabilirMi
  StrCmp $R0 "1" hrma_dizin_tamam
  Pop $R0
  DetailPrint "HRMA: '$INSTDIR' bos degil ve bir HRMA kurulumu degil."
  MessageBox MB_OK|MB_ICONSTOP "Kurulum durduruldu.$\r$\n$\r$\n'$INSTDIR' bos degil ve bir HRMA kurulumu degil (${HRMA_IMZA} yok).$\r$\nHRMA bu dizindeki app, libs ve python klasorlerini silecekti.$\r$\nLutfen bos bir dizin ya da mevcut bir HRMA kurulumu secin." /SD IDOK
  Abort "Hedef dizin dogrulanamadi: $INSTDIR"
  hrma_dizin_tamam:
  Pop $R0

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
  CreateShortCut "$DESKTOP\HRMA.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "HRMA - Rocket Motor Analysis"
  CreateDirectory "$SMPROGRAMS\HRMA"
  CreateShortCut "$SMPROGRAMS\HRMA\HRMA.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\launcher.py"' "$INSTDIR\hrma.ico" 0 SW_SHOWNORMAL "" "HRMA - Rocket Motor Analysis"

  ; Kaldırıcı + Program Ekle/Kaldır kaydı
  ; Kurulum imzası: kaldırma bu dosyayı GÖRMEDEN $INSTDIR'a dokunmaz
  ; (P10B3-23). İçerik insan tarafından da okunabilir olsun diye yazılır.
  FileOpen $0 "$INSTDIR\${HRMA_IMZA}" w
  FileWrite $0 "HRMA ${VERSION} - ${COMPANY}$\r$\n"
  FileWrite $0 "Bu dosya kaldirma isleminin hedef dizini dogrulamasi icin$\r$\n"
  FileWrite $0 "yazilmistir. SILMEYIN: yoksa kaldirici bu dizine dokunmaz.$\r$\n"
  FileClose $0

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

  ; P10B3-23: $INSTDIR KOŞULSUZ silinmez. Kurulum imzası yoksa dizin bize ait
  ; değildir (kullanıcı Browse ile başka bir klasör seçmiş ya da imza elle
  ; silinmiş olabilir) — o durumda yalnız kendi alt ağaçlarımız kaldırılır ve
  ; kök dizin OLDUĞU GİBİ bırakılır. Silinemeyen bir şey varsa uyarı basılır;
  ; "temizledim" hükmü kazanılmadan verilmez.
  IfFileExists "$INSTDIR\${HRMA_IMZA}" bizim_kurulum yabanci_dizin

  bizim_kurulum:
    RMDir /r "$INSTDIR\app"
    RMDir /r "$INSTDIR\libs"
    RMDir /r "$INSTDIR\python"
    Delete "$INSTDIR\hrma.ico"
    Delete "$INSTDIR\${HRMA_IMZA}"
    Delete "$INSTDIR\uninstall.exe"
    RMDir "$INSTDIR"          ; yalnız BOŞSA siler (özyinelemeli DEĞİL)
    Goto kaldirma_bitti

  yabanci_dizin:
    ; --- ÖH D20 / OH-D19-04 (Fable-D17 hüküm-7, P10B3-23 kalıntısı) --------
    ; ÖLÇÜLDÜ (taban 14acd1d, `docs/scofield/raw/OH/D20/app-api/a1/once.json`:
    ; `yabanci_dal_rmdir_n` = 3, `yabanci_dal_dogrulama_var` = false):
    ; KURULUM tarafındaki kapı D19'da kapandı, ama KALDIRMA tarafında bu dal
    ; "bu dizin bize ait DEĞİL" hükmünü verdikten SONRA yine de üç alt ağacı
    ; koşulsuz `RMDir /r` ile siliyordu. Kullanıcı imzayı elle sildiyse ya da
    ; $INSTDIR ortak bir klasörse oradaki `app` / `libs` / `python` bizim
    ; olmayabilir — "bize ait değil" deyip silmek kendi hükmünü çiğnemektir.
    ; Artık her alt ağaç KENDİ kanıtıyla siliniyor; kanıt yoksa dokunulmuyor
    ; ve kullanıcıya neyin bırakıldığı SÖYLENİYOR (fail-closed).
    Push $R2
    DetailPrint "HRMA kurulum imzasi ($INSTDIR\${HRMA_IMZA}) bulunamadi."
    DetailPrint "Guvenlik icin yalniz HRMA'nin KANITLANAN alt agaclari"
    DetailPrint "kaldiriliyor; $INSTDIR dizinine DOKUNULMUYOR."
    StrCpy $R2 "1"                     ; kurulum duzeni kanitlandi mi
    IfFileExists "$INSTDIR\app\launcher.py" 0 yab_app_yabanci
      RMDir /r "$INSTDIR\app"
      Goto yab_python
    yab_app_yabanci:
      StrCpy $R2 "0"
      DetailPrint "  app: HRMA izi (app\launcher.py) yok -> DOKUNULMADI."
    yab_python:
    IfFileExists "$INSTDIR\python\pythonw.exe" 0 yab_python_yabanci
      RMDir /r "$INSTDIR\python"
      Goto yab_libs
    yab_python_yabanci:
      StrCpy $R2 "0"
      DetailPrint "  python: HRMA izi (python\pythonw.exe) yok -> DOKUNULMADI."
    yab_libs:
    ; `libs` icinde sabit adli bir HRMA dosyasi YOKTUR (icerigi pip ile
    ; doldurulur), bu yuzden ancak kurulum DUZENININ tamami (app + python)
    ; kanitlandiysa bizim sayilir. Kanit yoksa sayi uydurmak yerine birakilir.
    StrCmp $R2 "1" 0 yab_libs_yabanci
      RMDir /r "$INSTDIR\libs"
      Goto yab_kalanlar
    yab_libs_yabanci:
      DetailPrint "  libs: app/python izi kanitlanmadi -> DOKUNULMADI."
    yab_kalanlar:
    ; --- ÖH D26 / OH-D25-04 -------------------------------------------------
    ; Bu iki `Delete` KOŞULSUZDU. Dal, birkaç satır önce "$INSTDIR dizinine
    ; DOKUNULMUYOR" künyesini basıp ardından yabancı dizindeki `hrma.ico` ve
    ; `uninstall.exe` dosyalarını yine de siliyordu: kendi hükmünü çiğneyen
    ; bir beyan. Aynı kusurun `RMDir /r` ayağı D20'de onarılmıştı
    ; (OH-D19-04); `Delete` ayağı gözden kaçmıştı.
    ; Artık ikisi de `libs` ile AYNI kanıta bağlıdır: kurulum DÜZENİ
    ; ($R2 — app\launcher.py + python\pythonw.exe) kanıtlanmadıysa dosyalar
    ; BIRAKILIR ve neyin bırakıldığı kullanıcıya ADIYLA söylenir. Sayı ya da
    ; hüküm uydurulmaz (fail-closed).
    StrCmp $R2 "1" 0 yab_kalanlar_yabanci
      Delete "$INSTDIR\hrma.ico"
      Delete "$INSTDIR\uninstall.exe"
      Goto yab_kalanlar_bitti
    yab_kalanlar_yabanci:
      DetailPrint "  hrma.ico: app/python izi kanitlanmadi -> DOKUNULMADI."
      DetailPrint "  uninstall.exe: app/python izi kanitlanmadi -> DOKUNULMADI."
      DetailPrint "  Bu dosyalari elle silebilirsiniz: $INSTDIR"
    yab_kalanlar_bitti:
    Pop $R2

  kaldirma_bitti:
  DeleteRegKey HKCU "${UNINSTKEY}"
SectionEnd
