# Sürüm ve yayın

**Son güncelleme:** 2026-08-14
**Kapsam:** Sürüm numarasının nereden geldiği ve nerelerde eşitlendiği; sekiz
yayın kapısının ne ölçtüğü ve hangi olaydan doğduğu; etiketten taslak sürüme
giden otomasyon; yayın sonrası adımlar.
**Kapsam dışı:** Paketlerin nasıl derlendiği, macOS imza ayrıntısı ve uygulama
içi güncelleyicinin sözleşmesi — bunlar [`../RELEASE.md`](../RELEASE.md) ve
[`../../packaging/README.md`](../../packaging/README.md) içindedir ve burada
tekrar edilmez.

> **Yetki ayrımı (2026-08-14 ölçümü):** `docs/RELEASE.md` yayın adımlarını
> **elle** anlatır (`build_mac_app.sh` → `build_dmg.sh` → `makensis` →
> `publish_release.sh`) ve `packaging/release_gate.sh`'ten hiç söz etmez.
> Bugünkü asıl yol etiketle tetiklenen `.github/workflows/release.yml`'dir.
> Paket içeriği/imzası için `RELEASE.md`, **karar sırası ve kapılar** için bu
> belge esas alınır.

---

## 1. Sürüm numarası

### 1.1 Tek kaynak

```python
# hrma/__init__.py
__version__ = "2.6.26"     # 2026-08-14 ölçümü
```

Her derleme betiği sürümü bu dosyadan okur. Windows kurulumcusuna sürüm
`makensis -DVERSION=X.Y.Z` ile açıkça verilir ve `__init__.py` ile eşleşmek
zorundadır.

### 1.2 Numaralama deseni

Depoda yazılı bir sürüm politikası **yok**; uygulanan desen ölçüldü:

| Gözlem | Ölçüm |
|---|---|
| Etiket biçimi | `vX.Y.Z` (`git tag`: `v2.5.0` … `v2.6.2`, `v2.6.25`, `v2.6.26`) |
| Üçüncü hane | Hem düzeltme hem "kalite turu" için kullanılıyor: `2.6.2` → `2.6.25` → `2.6.26` → `2.6.27` |
| Karşılaştırma | Sayısal, dizgesel değil: `parse_version` her haneyi `int`'e çevirir, `is_newer` demetleri karşılaştırır — bu yüzden `2.6.25 > 2.6.2` doğru sonuç verir (`hrma/utils/update_checker.py:139`) |
| Ara kayıt etiketleri | `wip-*` deseni; yayın otomasyonunu tetiklemez (otomasyon yalnız `v*` dinler) |

Sürüm türü **sürüm notunda** anlatılır (örn. v2.6.26 changelog başlığı
"Quality release", "No new engineering features"), numarada kodlanmaz.

### 1.3 Numaranın eşitlendiği yerler

Kapı 1/8 aşağıdaki dördünü karşılaştırır; biri bile tutmazsa yayın durur:

1. `hrma/__init__.py` → `__version__`
2. `hrma/data/changelog.json` → `versions[0].version` (en üst girdi)
3. `packaging/release_notes_v<X.Y.Z>.md` → dosyanın **var olması**
4. `README.md` → indirme bağlantılarında `HRMA-Setup-<X.Y.Z>` geçmesi

Ayrıca `CITATION.cff` içindeki `version` / `date-released` yayın anında
güncellenir (`CONTRIBUTING.md` §5). Bu alan kapı tarafından **ölçülmüyor** —
elle yapılan tek eşitleme burasıdır.

---

## 2. Yayın kapısı: `packaging/release_gate.sh`

724 satır, 8 adım. Kapı **mekaniktir; ikna edilemez.** Çıkış kodu 0 ise yayın
serbest; değilse hangi kapının neden kapandığını adıyla söyler.

```bash
bash packaging/release_gate.sh              # tam kapı
TAKIMI_ATLA=1 bash packaging/release_gate.sh   # yalnız YEREL takım atlanır
```

| # | Adım | Ne ölçer | Hangi olaydan doğdu |
|---|---|---|---|
| 1/8 | **Sürüm tutarlılığı** | §1.3'teki dört yer | — |
| 2/8 | **Git durumu** | Çalışma ağacı temiz **ve** HEAD push edilmiş (üst akışla aynı) | Commit edilmemiş değişiklikle çıkan sürüm, kaynağı olmayan ikili demektir |
| 3/8 | **Yapı ↔ commit zaman sırası** | Artefakt mtime, commit'in *committer* tarihinden eski olamaz; **ve** paketin içine gömülü `BUILD_INFO.json`'daki sha, HEAD ile aynı olmalı | v2.6.25: DMG+EXE, temsil ettiği commit'ten **36 dk 51 sn önce** üretilmişti; indirilen paket sürüm notundaki düzeltmelerin hiçbirini içermiyordu. `mtime` tek başına yetmez — `touch` bile onu tazeler |
| 4/8 | **GitHub Actions (bu commit)** | Bu SHA'nın **bütün** koşuları tamamlanmış ve yeşil mi. **Atlanamaz** | v2.6.2: CI kırmızı bittikten 14 dakika sonra yayın yapıldı, uygulama kullanıcının makinesinde hiçbir hesap yapmadı |
| 5/8 | **Tam test takımı** | Argümansız `pytest` (yaklaşık 15 dk). Alt küme koşturmak bu kapıyı **geçmiş saymaz** | v2.6.2: yalnız 25 kontrollük bir özellik kapısı koşulup "25/25" denmişti; 17 hatanın 15'i yerelde de düşüyordu |
| 6/8 | **Canlı duman testi — varsayılan olmayan portta** | Gerçek sunucu (port 8087), tarayıcı gibi `Origin` başlığı, gerçek hesap; yanıt **gövdesi** denetlenir (`plots.performance`, `nozzle_design.performance.exit_mach > 1`) | v2.6.2'yi kullanılamaz yapan 403'ü hiçbir test yakalayamazdı: test de kod da portun 8080 olduğunu varsayıyordu. Ayrıca yalnız HTTP 200'e bakmak yetmiyordu — boş gövde de 200 döner |
| 7/8 | **macOS paket imzası** | Derlenmiş `.app` (`--deep`), DMG içindeki uygulama (mount üstünde `--deep`), ve xattr'ları sıyrılmış kopyada tam `--verify --deep --strict` | v2.6.0-2.6.2 **imzasız** yayınlandı; eski `codesign` satırı `2>/dev/null \|\| true` ile kendi hatasını yutuyordu. macOS Tahoe'da uygulama açılmıyor ve güncelleyici kullanıcıyı eski sürüme geri alıyordu |
| 8/8 | **Paket içerik manifesti + boyut sapması** | Paketin **içinde** olması gerekenler tek tek sayılır (örn. `examples/*.hrma` sayısı depodakiyle aynı olmalı) ve artefakt boyutu bir önceki yayınla karşılaştırılır | Yayınlanan DMG mount edildiğinde `examples/` dizini yoktu, oysa `examples/README.md` kullanıcıya o dosyaları kopyalamasını söylüyordu. Ayrıca bir önceki sürümde DMG 526 MB'den 383 MB'ye düşmüş (bytecode ön-derleme kaybı) ve kimse fark etmemişti |

**Yalnız 5/8 atlanabilir** (`TAKIMI_ATLA=1`), çünkü CI aynı takımı temiz
makinede koşar ve 4/8 bunu zaten sınar. CI kontrolü atlanamaz.

### 2.1 Kapıyı atlamanın tek meşru yolu

```bash
TASLAK=1 KAPIYI_ATLA=1 KAPIYI_ATLA_GEREKCE="..." bash packaging/publish_release.sh
```

* Atlama **yalnız taslak** sürümlerde geçerlidir; herkese açık sürüm kapı
  atlanarak üretilemez.
* Gerekçe zorunlu ve en az 20 karakter.
* Gerekçe iki yere yazılır: `packaging/release_gate_bypass.log` ve **taslağın
  kendi gövdesi**. (2026-08-14 ölçümü: log dosyası depoda yok — bugüne kadar
  atlama kullanılmamış.)

---

## 3. Yayın öncesi kapı ölçütleri (kapının ölçmediği kısım)

Kapı mekanik olanı ölçer. Aşağıdakiler **insan kararıdır** ve kampanya
planlarından ölçüldü (`V2.6.26_BITIRME_PLANI` Faz 7,
`YOL_HARITASI_2.7_VE_SONRASI` §"Her kalem için değişmez kural"):

- [ ] Bağlama haritası yeşil: ölü alan 0, ölçülemedi 0, yankı yalnız beyanlı
- [ ] `docs/BULGU_KAYIT_DEFTERI.md` açık borç listesi gözden geçirildi ve
      gerekçeleri hâlâ geçerli
- [ ] Yeni modüller doğrulama kümesiyle geldi (analitik / yayımlanmış veri /
      korunum) — doğrulaması olmayan modül yayımlanmaz
- [ ] Sürüm notları **iki dilli** (EN+TR) ve changelog girdisiyle uyumlu
- [ ] `USER_MANUAL.md` ve `README.md` yeni davranışı anlatıyor
- [ ] Doğrulanmamış iş varsa (örn. yalnız tek platformda denenmiş) sürüm
      notunda **açıkça beyan edildi**

---

## 4. Otomasyon: etiketten taslak sürüme

Ayrıntı: [`../dev/yayin_otomasyonu.md`](../dev/yayin_otomasyonu.md).
İş akışı: `.github/workflows/release.yml`.

**Tek cümle:** `v*` etiketi push edilir, runner'lar `.dmg` ve `.exe`
paketlerini *etiketlenen ağaçtan* derler, doğrulamalar koşar, sonuçta
**taslak** bir GitHub sürümü açılır. Taslağı yayına çevirme kararı insandadır.

### 4.1 İşler ve kapı karşılıkları

| İş | Adı | Kapı karşılığı | Nerede koşar |
|---|---|---|---|
| `surum-baglantisi` | Etiket ↔ paket sürümü ↔ changelog ↔ sürüm notu ↔ README | 1/8 | ubuntu |
| `testler` | Tam takım + canlı duman | 5/8, 6/8 | ubuntu |
| `ci-durumu` | `tests` iş akışı bu SHA'da yeşil mi | 4/8 | ubuntu |
| `mac-paket` | `.app` + `.dmg`, köken kaydı ve imza | 3/8, 7/8 | **self-hosted macOS** |
| `win-paket` | payload + `.exe` | 3/8 | ubuntu |
| `taslak-yayin` | Taslak sürüm + artefakt yükleme | — | ubuntu |
| `yayin-denetimi` | Yayın ↔ commit ↔ CI zaman sırası (yayın **sonrası**) | 3/8, 4/8'in aynası | ubuntu |

`surum-baglantisi` bilerek en başta ve en ucuzdur: yanlış etiketlenmiş bir ağaç
için bir saatlik paketleme başlatmanın anlamı yok.

### 4.2 Bilinçli tasarım kararları

* **`pull_request` tetikleyicisi yok.** macOS işi self-hosted bir runner'da,
  yani geliştiricinin kendi makinesinde koşuyor. Depo herkese açık; fork'tan
  gelen bir PR bu iş akışını tetikleyebilseydi yabancı kod o makinede
  çalışırdı. Etiket push'u yalnız yazma yetkisi olanın yapabileceği bir
  eylemdir.
* **Eşzamanlılık: sıraya girer, iptal etmez.** Aynı etiket için ikinci bir
  koşu self-hosted runner'ın çalışma dizinini ortasından böler; yarım kalan
  derleme elde kalan artefakti belirsizleştirir.
* **Derleme girdileri özetle pinlenir** (`PBS_MAC_SHA256`, `WIN_EMBED_SHA256`).
  Bunlar sürüm numarası değil **dosya kimliğidir**: girdi değişirse iş kırmızı
  olur ve pinin bilinçli güncellenmesini bekler. Sessiz runtime kayması böyle
  engellenir. Windows gömülü Python'unun özeti python.org'un yayımladığı
  dosyayla **bayt bayt aynı** olduğu ölçüldü.
* **Neden otomasyon:** v2.6.26'da yayın kapısı artefakt tazeliğini ölçmeye
  başlayınca her düzeltme commit'i o ölçümü sıfırladı ve `dmg` + `exe` **elle
  dört kez** yeniden derlendi. İnsan eli derlediği sürece "bu ikili hangi
  ağacı temsil ediyor?" sorusu her commit'te yeniden açılır.

### 4.3 Kapsam dışı bırakılan güvence (bilinçli)

Apple Developer ID imzası / notarization, Authenticode, tedarik zinciri kanıtı
(TUF/Sigstore). macOS imzası **ad-hoc**'tur (`codesign -s -`); Gatekeeper'ın
`spctl --assess` denetimi ad-hoc paketleri tasarım gereği reddeder, bu yüzden
kabul ölçütü `codesign --verify --deep --strict`'tir.

---

## 5. Yayın sonrası

1. `publish_release.sh` `README.md` içindeki indirme bağlantılarını yeni
   sürüme çevirir — **bu değişiklik commit edilmelidir**.
2. `CITATION.cff` içindeki `version` ve `date-released` güncellenir.
3. Etiket yerelde de bulunmalı: 2026-08-14 ölçümünde `v2.6.26` etiketi
   **uzakta var, yerelde yok** (`git tag` listesi `v2.6.25`'te bitiyor).
   Yayın sonrası `git fetch --tags` alışkanlığı yoksa yerel geçmiş sürümü
   göstermez.
4. `yayin-denetimi` işi yayın sonrası zaman sırasını bir kez daha ölçer.
5. Kullanıcıdaki uygulama sürümü GitHub Releases API'sinden bulur ve
   platforma göre **dosya sonekiyle** seçer (`.dmg` / `.exe`). Bu yüzden varlık
   adlandırması bir **sözleşmedir**: bu iki varlığı taşımayan sürüm, kurulu
   uygulamalara hiç önerilmez (ayrıntı `RELEASE.md`).

---

## 6. Yayın kontrol listesi

- [ ] `hrma/__init__.py`, changelog, `packaging/release_notes_v*.md`, README
      sürümü aynı
- [ ] Çalışma ağacı temiz ve push edilmiş
- [ ] `tests` iş akışı bu SHA'da yeşil
- [ ] Sürüm notu iki dilli, doğrulanmamış iş beyanlı
- [ ] `git tag vX.Y.Z && git push origin vX.Y.Z` → otomasyon çalıştı
- [ ] Taslak sürümdeki varlıklar: `HRMA-Setup-X.Y.Z-macOS.dmg` **ve**
      `HRMA-Setup-X.Y.Z.exe`
- [ ] Taslak insan tarafından incelendi, sonra yayına çevrildi
- [ ] README bağlantı commit'i + `CITATION.cff` güncellemesi
- [ ] `git fetch --tags` ile yerel etiket senkron
