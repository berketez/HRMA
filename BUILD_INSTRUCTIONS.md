# UZAYTEK HRMA - Build Instructions

Bu dosya, UZAYTEK Hybrid Rocket Motor Analysis uygulamasını Windows ve macOS için standalone executable'lara dönüştürme talimatlarını içerir.

## Gereksinimler

### Python Gereksinimleri
```bash
pip install -r requirements.txt
```

### Platform Özel Gereksinimler

#### Windows
- Windows 10 veya üzeri
- PyInstaller
- NSIS (isteğe bağlı, installer için)

#### macOS
- macOS 10.15 (Catalina) veya üzeri
- PyInstaller
- Xcode Command Line Tools
- Developer Certificate (code signing için, isteğe bağlı)

## Build Talimatları

### Windows Executable (.exe) Oluşturma

1. **Build scriptini çalıştır:**
```bash
python build_windows.py
```

2. **Çıktı dosyaları:**
- `dist/UZAYTEK_HRMA.exe` - Ana executable
- `dist/UZAYTEK_HRMA_Distribution/` - Dağıtım paketi
- `installer.nsi` - NSIS installer scripti

3. **Installer oluşturma (isteğe bağlı):**
```bash
makensis installer.nsi
```

### macOS App Bundle (.app) Oluşturma

1. **Build scriptini çalıştır:**
```bash
python build_macos.py
```

2. **Çıktı dosyaları:**
- `dist/UZAYTEK HRMA.app` - App bundle
- `UZAYTEK_HRMA_Installer.dmg` - DMG installer

## Manuel Build (PyInstaller)

### Windows
```bash
pyinstaller --onefile --windowed --name=UZAYTEK_HRMA --add-data="templates;templates" --add-data="static;static" desktop_app.py
```

### macOS
```bash
pyinstaller --onedir --windowed --name="UZAYTEK HRMA" --add-data="templates:templates" --add-data="static:static" desktop_app.py
```

## Test Etme

### Desktop Uygulamasını Test Et
```bash
python desktop_app.py
```

### Web Uygulamasını Test Et
```bash
python app.py
```

## Dağıtım

### Windows
- `UZAYTEK_HRMA.exe` dosyasını kullanıcılara dağıt
- Veya `UZAYTEK_HRMA_Installer.exe` installer'ını kullan

### macOS
- `UZAYTEK_HRMA_Installer.dmg` dosyasını dağıt
- Kullanıcılar uygulamayı Applications klasörüne sürükleyebilir

## Güvenlik Notları

### Windows
- Antivirus programları ilk çalıştırmada uyarı verebilir
- Code signing sertifikası kullanılması önerilir

### macOS
- İlk çalıştırmada güvenlik uyarısı çıkabilir
- Notarization yapılması önerilir
- Kullanıcılar System Preferences > Security & Privacy'den izin verebilir

## Sorun Giderme

### Build Hataları
1. Tüm bağımlılıkların yüklendiğinden emin olun
2. Python sürümünün 3.8+ olduğunu kontrol edin
3. Virtual environment kullanın

### Runtime Hataları
1. Tüm dosyaların executable ile birlikte paketlendiğini kontrol edin
2. Port çakışmalarını kontrol edin
3. Firewall ayarlarını kontrol edin

## Performans Optimizasyonu

### Executable Boyutunu Küçültme
1. Gereksiz modülleri kaldır
2. `--exclude-module` parametresi kullan
3. UPX kullanarak sıkıştır

### Başlangıç Hızını Artırma
1. `--onedir` yerine `--onefile` kullan
2. Lazy import kullan
3. Gereksiz import'ları kaldır

## Versiyon Notları

### v1.0
- İlk standalone executable build
- Windows .exe desteği
- macOS .app bundle desteği
- DMG installer
- NSIS installer scripti

## İletişim

Teknik destek için: berketezgocen@hotmail.com

---
© 2025 UZAYTEK. Tüm hakları saklıdır.