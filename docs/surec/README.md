# HRMA süreç dokümantasyonu

**Son güncelleme:** 2026-08-14
**Kapsam:** Bu dizin HRMA'nın **nasıl geliştirildiğini** anlatır: bir işin baştan
sona akışı, test disiplini, sürüm ve yayın kapıları, kod değişikliği prosedürü.
**Kapsam dışı:** Ürünün ne yaptığı (`README.md`), nasıl kullanıldığı
(`docs/USER_MANUAL.md`), fiziğin nasıl türetildiği (`docs/bolum*.md`), neyin
doğrulanmış sayıldığı (`docs/VALIDATION_STATUS.md`). Bu dizin bir yol haritası
da değildir — ne yapılacağı `docs/YOL_HARITASI_2.7_VE_SONRASI.md` içindedir.

---

## 1. Bu dizindeki belgeler

| Belge | Neyi cevaplar |
|---|---|
| [`gelistirme-akisi.md`](gelistirme-akisi.md) | Bir bulgu nereden gelir, nasıl ölçülür, nasıl kapanır, hangi commit'e girer |
| [`test-disiplini.md`](test-disiplini.md) | Hangi test türü ne yakalar, "kusuru koruyan bekçi" nedir, eşik ne zaman değiştirilebilir (cevap: neredeyse hiç) |
| [`surum-ve-yayin.md`](surum-ve-yayin.md) | Sürüm numarası nereden gelir, 8 yayın kapısı ne ölçer, etiketten taslak sürüme giden otomasyon |
| [`kod-degisiklik-proseduru.md`](kod-degisiklik-proseduru.md) | Değişiklik öncesi/sonrası zorunlu adımlar, riskli dosyalar, geri alma |

Bu dört belge birbirini tekrar etmez. Aynı konunun farklı yüzleri şuraya düşer:

* Bekçi testinin **ne olduğu** → `test-disiplini.md`
* Bekçinin akışın **neresinde** yazıldığı → `gelistirme-akisi.md`
* Bekçisiz değişikliğin **niçin kabul edilmediği** → `kod-degisiklik-proseduru.md`

## 1.1 Canlılık kuralı (ZORUNLU)

`docs/surec/`, `docs/kapsam/` ve `docs/mimari/` **yaşayan belgelerdir**;
tarihî kayıt değildir. Kural:

1. Bir oturumda bu belgelerin anlattığı gerçek DEĞİŞTİYSE (yeni modül
   bağlandı, kapı ölçütü değişti, sözleşme alanı eklendi, yol haritası
   kalemi kapandı), ilgili belge **aynı oturumda** güncellenir ve başındaki
   "Son güncelleme" tarihi o güne çekilir. Oturum sonuna bırakılmaz.
2. Belge ile kod çelişiyorsa **kod kazanır**: belge ölçülerek düzeltilir,
   asla "belgeye uydurmak için" kod değiştirilmez.
3. Yalnız değişen bölüm düzenlenir; belge baştan yazılmaz. Eski bilgi
   tarihli not olarak korunabilir ("2026-08-14'e kadar ... idi").
4. Satır numarası atıfları çürür (ölçüldü: 12 günde 4 bağdan 3'ü kaydı —
   `formal/registry.json` vakası). Aktif geliştirilen dosyalara atıf
   **sembol adıyla** verilir, satır numarasıyla değil.

---

## 2. Bu dizinin dışındaki süreç kaynakları

Süreç zaten kısmen yazılıydı. Aşağıdakiler **hâlâ geçerlidir**; bu dizin onları
kopyalamaz, birleştirir ve aralarındaki boşlukları doldurur.

| Kaynak | Rolü | Dil |
|---|---|---|
| [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) | Dışarıdan katkı verenin sözleşmesi: kurulum, testi koşma, PR ölçütleri | İngilizce |
| [`../BULGU_KAYIT_DEFTERI.md`](../BULGU_KAYIT_DEFTERI.md) | Kapatılan her kusurun bekçisine bağlandığı defter + bekçi katmanları tablosu | Türkçe |
| [`../RELEASE.md`](../RELEASE.md) | Paket üretimi, macOS imzası, uygulama içi güncelleyicinin sözleşmesi | İngilizce |
| [`../../packaging/README.md`](../../packaging/README.md) | Derleme betiklerinin ayrıntısı | — |
| [`../STANDART_ATIFLARI.md`](../STANDART_ATIFLARI.md) | Kodun attığı her standardın tam adı ve doğrulama durumu | Türkçe |
| [`../VALIDATION_STATUS.md`](../VALIDATION_STATUS.md) | Neyin doğrulandığı, neyin doğrulanmadığı — fizik değiştirmeden önce okunur | İngilizce |
| [`../V2.6.26_BITIRME_PLANI.md`](../V2.6.26_BITIRME_PLANI.md) | Faz + kapı yönteminin uygulandığı somut örnek (Faz 0-7) | Türkçe |
| [`../YOL_HARITASI_2.7_VE_SONRASI.md`](../YOL_HARITASI_2.7_VE_SONRASI.md) | İş kırılımı (A-F kulvarları) ve her kalem için değişmez kurallar | Türkçe |
| [`../dev/`](../dev/) | Ölçüm çıktıları: bağlama haritaları, parti dosyaları, tarayıcı denetim raporu, yayın otomasyonu notu | Türkçe |
| [`../../.pre-commit-config.yaml`](../../.pre-commit-config.yaml) | Hızlı denetimler (sözdizimi, dosya hijyeni, iddia dili) | — |

---

## 3. Ölçülen anlık durum (2026-08-14)

Aşağıdaki sayıların hepsi bu tarihte depoda **ölçüldü**. Yanlarındaki komutla
yeniden üretilebilirler; eskimişlerse komut yeniden koşulur, sayı elle
güncellenmez.

| Ölçüm | Değer | Komut |
|---|---|---|
| Paket sürümü | `2.6.26` (ağaç 2.6.27 geliştirmesinde) | `grep __version__ hrma/__init__.py` |
| Toplanan test | **6549** (toplama süresi 52 s) | `python3 -m pytest --collect-only -q \| tail -3` |
| Test dosyası (`tests/*.py`) | 219 dosya, 85 788 satır | `ls tests/*.py \| wc -l`, `wc -l tests/*.py \| tail -1` |
| Test alt dizinleri | `fea/`, `flow/`, `fixtures/`, `support/` | `ls -d tests/*/` |
| CI iş akışı | 2 adet: `tests.yml`, `release.yml` | `ls .github/workflows/` |
| Yayın kapısı | 8 adım, 724 satır | `grep -c "" packaging/release_gate.sh` |
| `tools/` betikleri | 8 Python dosyası (6'sı süreç aracı, 2'si varlık üretimi) | `ls tools/*.py` |
| Dal | yalnız `main` (uzak: `origin/main`) | `git branch -a` |
| Push edilmemiş commit | 3 | `git rev-list --count origin/main..HEAD` |

Sürümlerin tam takım süresi bu turda ölçülmedi; `CONTRIBUTING.md` yerelde
15-20 dakika olduğunu bildiriyor ve yayın kapısı 5/8 adımı da bu süreyi
varsayıyor.

---

## 4. Bu belgelerin uyduğu kural

Depodaki süreç belgelerinin tamamı tek bir kurala uyar ve bu dizin de ona
uyar:

> **Ölçülmemiş cümle yazılmaz.** Bir sayı yazılıyorsa nereden geldiği ve nasıl
> yeniden üretileceği yanında durur. "Muhtemelen", "genelde", "yaklaşık olarak
> bilindiği üzere" ile başlayan cümle bu depoda bilgi sayılmaz.

Bunun sebebi kozmetik değil: HRMA'nın en pahalı hata sınıfı **makul görünen ama
hesaplanmamış sayı**. Aynı disiplin koda uygulanıyorsa dokümantasyonda
gevşetilemez.

---

## 5. Ölçüm anındaki tutarsızlıklar

Bu dizin yazılırken var olan belgeler ölçümle karşılaştırıldı. Aşağıdaki üç
tutarsızlık **tespit edildi ve düzeltilmedi** (bu dizinin yazma yetkisi
dışındalar). Kaydı burada duruyor ki sessizce eskimesinler.

| Nerede | Belgede yazan | Ölçülen | 
|---|---|---|
| `CONTRIBUTING.md` §5 | "7 gates, all must pass" | `packaging/release_gate.sh` **8** adım basıyor (`1/8` … `8/8`) |
| `docs/BULGU_KAYIT_DEFTERI.md` §"Sürüm öncesi kapı" | 6 maddelik kapı listesi | Aynı betikte 8 adım; canlı duman testi ve paket içerik manifesti listede yok |
| `docs/RELEASE.md` | Yayın adımları elle: `build_mac_app.sh` → `build_dmg.sh` → `makensis` → `publish_release.sh` | Asıl yol artık etiketle tetiklenen `.github/workflows/release.yml` (taslak sürüm üretir); `release_gate.sh` `RELEASE.md`'de hiç geçmiyor |

Ayrıca `docs/README.md` dizin listesi bu dizindeki belgeleri ve
`BULGU_KAYIT_DEFTERI.md`, `STANDART_ATIFLARI.md`, `YOL_HARITASI_2.7_VE_SONRASI.md`
dosyalarını içermiyor; güncellenmesi gerekiyor.
