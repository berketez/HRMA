# HRMA Kurulum Paketleri Üretimi

Tek tıkla kurulan paketler. Her iki paket de **internet
gerektirmez** — Python 3.12 runtime'ı ve TÜM bağımlılıklar (build123d/OCC,
CoolProp, rocketcea, kaleido...) gömülüdür. Çıktılar `dist/` dizinine düşer
(git'e girmez).

## Üretim (tamamı macOS üzerinde çalışır — Windows makinesi GEREKMEZ)

```bash
# 0) Gerekli araçlar: brew install makensis  (NSIS, exe'yi Mac'te derler)
#    Python 3.12 (anaconda base kullanıldı — pip cross-platform indirme yapar)

# 1) Runtime'ları indir:
#    - python-build-standalone cpython-3.12 aarch64-apple-darwin install_only.tar.gz → runtime/pbs-mac.tar.gz
#    - python.org python-3.12.10-embed-amd64.zip → runtime/python-embed-win.zip

# 2) Bağımlılık payload'ları (requirements_bundle.txt pinli):
python3 -m pip install --target mac/libs -r requirements_bundle.txt
python3 -m pip install --target mac/libs --no-deps build123d==0.11.1 ocp-gordon==0.2.0
bash build_win_payload.sh          # win_amd64 wheel'leriyle win/payload üretir

# 3) macOS: .app + DMG
bash build_mac_app.sh              # HRMA.app (bundled python + libs + app)
bash test_bundle_mac.sh            # import + sunucu duman testi (zorunlu)
bash build_dmg.sh                  # dist/HRMA-Setup-X.Y.Z-macOS.dmg (sürümü hrma/__init__.py'den okur)

# 4) Windows: NSIS installer (Mac üstünde cross-compile)
#    -DVERSION zorunlu: verilmezse hrma.nsi "0.0.0-dev" adlı exe üretir.
#    Sürümün tek kaynağı hrma/__init__.py — oradaki __version__ değerini geçir.
makensis -DVERSION=X.Y.Z hrma.nsi  # HRMA-Setup-X.Y.Z.exe

# 5) Yayın (sürüm bump → build → publish sırası):
#    a) hrma/__init__.py içinde __version__ değerini yükselt
#    b) Yukarıdaki 3. ve 4. adımlarla dmg + exe'yi yeni sürümle derle
#    c) GitHub Release oluştur + README indirme linklerini güncelle:
bash publish_release.sh "Sürüm notları..."
```

### Yayın sırası (3.0.6'dan itibaren: etiket yayınlanan commit'e açılır)

1. Yayın commit'i aday dalına push edilir; `tests` iş akışı o SHA'da yeşil biter.
2. Paket ağacının üst akışı o aday dalıdır (kapı 2/10 `HEAD == @{u}` ister).
3. `publish_release.sh` kapıyı koşturur, HEAD SHA'sını kapıdan önce okur ve
   `gh release create --target <SHA>` ile etiketi TAM O commit'e açar. Uzakta
   aynı adlı etiket başka bir commit'i gösteriyorsa yayın yapılmaz (gh o durumda
   `--target`'ı yok sayardı).
4. `main` yayından SONRA taşınır. main push'u `tests`'i aynı SHA için yeniden
   tetiklerse kapı 4/10 o süren kopyayı beklemez (yeşil kopya varsa BİLGİ satırı);
   iptal edilmiş/başarısız koşu yine KALDI.

v3.0.5'te (28 Eki) etiket `--target`'sız açıldığı için main yayından önce push
edildi ve kapı aynı commit'in ikinci `tests` koşusunu ~57 dk bekledi.

## Kritik kararlar (değiştirmeden önce oku)

- **numpy==1.26.4 pini zorunlu** (repo requirements.txt notu). `build123d` ve
  `ocp-gordon` metadata'da numpy>=2 deklare eder ama 1.26.4 ile çalıştıkları
  kanıtlı → bu ikisi **--no-deps** ile kurulur.
- **kaleido==0.2.1 + plotly==6.0.1** çifti test edilmiş kombinasyon.
- **rocketcea**: Windows'ta PyPI wheel var (1.2.1); macOS wheel'i YOK →
  build_mac_app.sh çalışan anaconda ortamından derlenmiş kopyayı alır
  (arm64 + numpy 1.26.4 ABI eşleşmesi şart).
- **macOS Terminal yalnız `.command` uzantılı dosyayı çalıştırır** — .app
  başlatıcısındaki runner dosyası bu yüzden .command'dir (2026-07-13 tespiti).
- **Windows kurulumu per-user** ($LOCALAPPDATA\HRMA): yönetici istemez,
  uygulama dizini yazılabilir (data/ sqlite + cache oraya yazıyor).
- Kullanıcının dışa aktardığı rapor, CAD ve çizim dosyaları kaydetme
  penceresiyle kaydedilir; pencere **İndirilenler** klasöründe açılır
  (pywebview 6.2.1: macOS `NSDownloadsDirectory`, Windows İndirilenler
  bilinen klasörü). **Belgeler/HRMA** (menü: Open Output Folder;
  launcher.py cwd'yi oraya alır) proje dosyalarını (`projects/`) ve
  Windows'ta günlüğü (`hrma_log.txt`) tutar; CAD üreticileri artık
  her istekte kendi geçici dizinine yazar, `cad_exports/` boş kalır.
- launcher.py: port 8080-8090 tarar, HRMA zaten çalışıyorsa ikinci kopya
  açmaz; HRMA_PORT env ile port zorlanabilir (destek senaryosu).

## Bilinen sınırlar

- Paketler **imzasız**: Windows SmartScreen "Ek bilgi → Yine de çalıştır",
  macOS Gatekeeper "sağ tık → Aç" ister (OKU_BENI dosyaları ekibe verilecek).
- macOS paketi **Apple Silicon (arm64)** içindir; Intel Mac'te çalışmaz.
- Windows exe Mac'te derlendi; ilk gerçek Windows testi 4090 kurulunca yapılmalı.
