# Faz 1 — parti sahibi ajan talimatı

Bu belge 138 kusuru kapatacak her parti sahibinin uyacağı sözleşmedir. Ajan
prompt'una bu dosya referans verilir; kurallar burada tek noktada durur.

---

## 1. Sana ait olan

`docs/dev/kusur_partileri.json` içinde senin partin var. Yalnız o partinin
`dosyalar` listesindeki dosyalara **yazarsın**. Başka her dosya senin için
salt-okunurdur — okuyabilirsin, düzenleyemezsin.

Bu keyfi bir kural değil: partiler, aynı dosyaya iki ajanın yazmaması için
ölçümden üretildi. Sınırı aşarsan başka bir ajanın işi sessizce kaybolur
(14 Mayıs 2026'da tam olarak bu oldu, bir günlük iş gitti).

Partin dışında bir dosyanın değişmesi gerektiğini görürsen: **değiştirme**,
raporunda "şu dosyada şu değişiklik gerekiyor" diye bildir. Ana model yapar.

---

## 2. Bir kalem nasıl kapanır

Rapordaki her kalem, çıktıda **sabit kalmış bir değer**dir: kullanıcı girdiyi
değiştiriyor ama o yaprak kıpırdamıyor. Kapatmak = o yaprağı gerçek hesaba
bağlamak. Dört adımın dördü de zorunlu:

### Adım 1 — ÖNCE ölç
Kalemin şu anki değerini kendi gözünle gör. Rapordaki `deger` alanına
güvenme, **koş ve bak**. Uygulamanın test istemcisiyle ilgili uç noktaya
(`/calculate`, `/calculate_solid`, `/calculate_liquid`) taban yükü gönder,
`yol` alanındaki JSON yaprağını oku, değeri not et.

### Adım 2 — İddiayı doğrula
Kalemin `mevcut_fonksiyon` alanı doluysa, o fonksiyonun **gerçekten var
olduğunu ve ne döndürdüğünü** `Grep`/`Read` ile teyit et. Rapor iddiaları
örneklemle sınandı ve tutarlı çıktı, ama tek tek doğrulama yine de senin
işin: imza değişmiş, fonksiyon başka bir şey hesaplıyor ya da rapor yanlış
dosyayı göstermiş olabilir.

`mevcut_fonksiyon` boşsa hesap yok demektir — yazman gerekir. O zaman
Adım 2 = fizik gerekçesini kaynağıyla yazmak (Sutton, NASA SP-xxxx, ASTM,
MMPDS...). **Kaynaksız katsayı uydurma.**

### Adım 3 — Bağla ve SONRA ölç
Değişikliği yap, sonra girdiyi oynat ve yaprağın **gerçekten değiştiğini**
göster. Rapordaki `onerilen_baglama` bir öneridir, emir değil — daha
doğrusunu bulursan onu yap ve gerekçesini yaz.

Çıktı formatın şu (raporunda her kalem için):

```
KALEM  .motor.structural_analysis.buckling.safety_factor
ÖNCE   inf  (thrust=0 geçiyordu)
SONRA  3 kN -> 0.62 MPa | 30 kN -> 0.83 | 100 kN -> 0.89
NASIL  hybrid_rocket_engine.py:1157 struct_input'a 'thrust': self.F eklendi
TEST   tests/test_buckling_wiring.py::test_thrust_reaches_buckling
```

### Adım 4 — Bekçi testi
Kalemin bir daha sabitlenmemesi için test yaz. Test, girdiyi iki farklı
değerde koşup çıktının **farklı** olduğunu doğrulamalı. Mevcut bekçi
ailesine ekle (`tests/test_*_wiring*.py`); yeni dosya açacaksan adı
`tests/test_<parti>_wiring_v2626.py` olsun.

---

## 3. Kapatamadığın kalem

Bir kalem kapanamıyorsa **uydurma değerle kapatma**. Üç meşru sonuç var:

| Sonuç | Ne zaman | Ne yaparsın |
|---|---|---|
| `REDDEDİLDİ` | Rapor yanılmış; değer gerçekten sabit olmalı (fiziksel sabit, birim dönüşümü, tanım gereği) | Gerekçeyi yaz, kalem listede kalır |
| `MODELLENMEDİ` | Hesabı yapacak fizik projede yok ve bu turda yazılamaz | Çıktıya `NOT_MODELLED` / `not_analyzed` etiketi koy — **sahte sayı değil** |
| `BAŞKA PARTİ` | Düzeltme senin dosyalarının dışında | Ne gerektiğini yaz, dokunma |

"Kapattım" demek için Adım 3'ün SONRA ölçümü elinde olmalı. Ölçüm yoksa
kalem kapanmamıştır.

---

## 4. Test koşma

**Tam suite'i koşma** — 1.5-2 saat sürüyor ve senin partin onu tek başına
haklı çıkarmaz. Bunun yerine:

```bash
# Kendi alanının testleri (örnek: sıvı partisi)
PYTHONPATH=. python3 -m pytest -p no:randomly -q tests/test_liquid*.py

# Dokunduğun modülü kullanan testler
PYTHONPATH=. python3 -m pytest -p no:randomly -q -k "injector or nozzle"
```

Tam suite faz kapısında **bir kez**, bütün partiler birleştikten sonra ana
model tarafından koşulur.

---

## 5. Yasaklar (bu projede kanla yazılmış)

- **Sahte veri, sahte gösterge, süs animasyon yok.** Hesaplanamayan alan boş
  kalır veya `NOT_MODELLED` der. Uydurma sayı üretmek en ağır kusurdur.
- **`shutil.rmtree` ve arkadaşları**: silme yolu mutlak ve önek denetimli
  olmalı. `os.path.dirname(göreli_yol)` → `"."` döner ve çalışma dizinini
  uçurur. Bu depo bu yüzden üç kez silindi.
- **Yapısal kod değişikliği metinsel `sed` ile yapılmaz** — AST kullan ya da
  Edit ile bağlamı görerek düzenle. Metinsel desen iki koşuda iki farklı yeri
  bozdu (cmd-41 dersi).
- **Sabit sayı iki dosyada tekrarlanmaz.** Yeni bir eşik/katsayı gerekiyorsa
  `hrma/constants.py`'ye koy, oradan import et. Aynı kavrama iki farklı ad
  verme.
- **Türkçe metinlerde aksan zorunlu**: "güncelleme", "açıklama" — ASCII'ye
  düşme. Kod sembolleri İngilizce kalır.

---

## 6. Raporun

Bitirince şunu döndür (metin, dosya değil):

1. **Özet satırı**: `P<n>: X kapandı / Y reddedildi / Z modellenmedi / W başka parti`
2. Her kalem için §2'deki 5 satırlık blok
3. Değiştirdiğin dosyaların listesi
4. Koştuğun testler ve sonuçları (sayıyla: `47 passed`)
5. Partin dışında değişmesi gerektiğini gördüğün şeyler

Kanıtsız cümle yazma. "Bağladım", "düzelttim", "artık çalışıyor" tek başına
kabul edilmez — önce/sonra sayısı ve test adı ister.
