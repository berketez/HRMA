# Doğrulama Kayıtları (gerçek deney veritabanı)

HRMA v2.5.0 "Güven Sürümü" — açık literatürdeki GERÇEK static-fire / uçuş /
motor-spec verisinin git-izlenen JSON veritabanı. Eski sentetik
`experimental_validation.py` katmanının (SQLite + 11 üretilmiş kayıt) halefidir;
sentetik kayıtlar 2026-07-17'de üretimden söküldü ve yalnız
`tests/fixtures/synthetic_experiments.json` içinde (`synthetic: true`) yaşıyor.

## Dizin düzeni

```
validation_records/
  SCHEMA.md          # kayıt şeması (tek doğruluk kaynağı: experiment_db.validate_record)
  README.md          # bu dosya
  hybrid/*.json      # hibrit motor kayıtları
  solid/*.json       # katı motor kayıtları
  liquid/*.json      # sıvı motor kayıtları
```

Kayıt başına bir dosya; dosya adı `test_id` ile aynı olmalıdır
(`<test_id>.json`). Alt klasör adı kaydın `motor_type` alanıyla uyuşmak
zorundadır (yükleyici uyuşmazlığı reddeder).

## Kayıt ekleme akışı (küratörlük)

1. Sayıyı KAYNAĞIN KENDİSİNDEN oku (tablo/metin); ikincil aktarımdan sayı
   alma. Şekilden sayısallaştırdıysan `digitized: true` +
   `source.extraction_note` yaz.
2. `SCHEMA.md`'ye göre kaydı yaz; sayıları orijinal birimleriyle, birim ekli
   anahtarlarla gir (`thrust_kgf`, `chamber_pressure_psia`, ...).
3. `inputs` / `measured` ayrımına dikkat: deneyde AYARLANAN büyüklük `inputs`,
   ÖLÇÜLEN sonuç `measured`. Aynı anahtar ikisinde birden olamaz.
4. Belirsizlik yalnız kaynak bildiriyorsa girilir; kapsam (k) bilinmiyorsa
   `coverage_k: null`.
5. Doğrula:

   ```bash
   python3 -c "from hrma.validation.experiment_db import load_records; \
               print(len(load_records()), 'kayit gecerli')"
   ```

6. `python3 -m pytest tests/test_experiment_db.py -q` yeşil olmalı.

## Yapısal kurallar (yükleyici zorlar)

- `synthetic: true` kayıt bu ağaçta YASAKTIR; bulunursa yükleme hata verir.
- `test_id` tüm ağaçta benzersizdir.
- İstatistik özetine (`experiment_db.summarize`) sentetik kayıt girmesi
  yapısal olarak imkansızdır (parametresi yoktur, koşulsuz dışlar).

## Mevcut tohum kayıtlar (G1)

| test_id | motor | Kaynak | confidence |
|---|---|---|---|
| `hyb-rezaei2018-htpb-n2o-t26` | hybrid | Rezaei, Soltani, Mohammadi, Scientia Iranica B 25(1), 2018 — Tablo 4 test 26 (HRMA'nın mevcut regresyon çapası) | high |
| `liq-rs25-109pct-spec` | liquid | L3Harris RS-25 spec sheet (07/2024, L26301) + NASA FS-2015-07-064-MSFC | high |

### G2 hibrit kampanya kayıtları (2026-07-17)

Tüm sayılar ARGE dosyasındaki tablolardan alındı ve bu küratörlük oturumunda
kaynak PDF'lerden (`HRMA-dogrulama-kaynaklari/`) yeniden teyit edildi.

| Kaynak | test_id deseni | Kayıt | confidence | Not |
|---|---|---|---|---|
| Rezaei 2018 (HTPB/N2O, Scientia Iranica B 25(1)) | `hyb-rezaei2018-htpb-n2o-t*` | 30 (+t26 = 31) | high | Tablo 4 (17 yeni) + Tablo 5 yakıt boyu serisi (11) + Tablo 3 tekrarlanabilirlik (ta2/ta3; A1 == t68 olduğu için ayrı girilmedi, çift sayım önlendi); Tablo 1 ölçüm belirsizlikleri her kayıtta |
| Karabeyoglu 2003 (Parafin SP-1a/GOX, AIAA 2003-1162, NASA Ames HCF) | `hyb-karabeyoglu2003-paraffin-gox-t*` | 26 | high | 8 kayıtta `anomaly.flag: true` (çatlak grain, lüle arızası/erozyonu, port yapısal arızası, kontrol arızası); grain boyu kaynakta test başına yok → `grain_length_in: null` + aday notu (33/45 inç) |
| Whitmore & Stoddard 2020 (GOX+Nytrox87/ABS, Aerospace 7(4):43) | `hyb-whitmore2020-*` | 5 | high (4) / medium (1) | 2 kampanya istatistiği (13+19 yakmanın mu/sigma/%95 seti; Nytrox c* 560.84 → 1560.84 `source.erratum`) + 2 kendi a-n fit'i + 1 literatür a-n derlemesi (6 kombinasyon, ikincil aktarım → medium) |
| Hansen & Edwards 2012 (Parafin-HTPB/N2O blowdown, UW SARP) | `hyb-hansen2012-paraffin-htpb-n2o-t2..t5` | 4 | high | usage_note: O/F~10 off-design — mutlak Isp kıyası için değil blowdown/Pc/enjektör dP doğrulaması için; t5'te `anomaly` (grain yapısal arızası, X-ray belgeli) |
| Wei ve ark. 2025 (PP/N2O + PP/Nytrox blowdown, Aerospace 12(5):372) | `hyb-wei2025-pp-{n2o,nytrox}-t*` | 11 | high | Oksitleyici sıcaklık taraması (6 saf N2O + 5 Nytrox); mdot_ox kaynakta test başına tablolaştırılmamış → alan girilmedi |
| Palacz & Cieślik 2023 (N2O/HDPE VFP, Aerospace 10(8):727) | `hyb-palacz2023-hdpe-n2o-t01..t11` | 11 | high | `out_of_hrma_geometry_scope`: motor balistiği korelasyonuna girmez; N2O besleme/blowdown doğrulaması + kapsam dışı geometri negatif örneği |

Toplam hibrit: 88 kayıt (72 motor-düzeyi static-fire + 2 kampanya istatistiği +
3 regresyon-fit kaydı + 11 kapsam-dışı VFP). Bilinçli dışarıda bırakılanlar:
McFarland 2019 (oksitleyici türü kaynakta adlandırılmamış — karantina),
Jens 2019 (slab yakıcı, motor-düzeyi satır yok), Zilliac 2006 (a-n derlemesi
UQ önseli olarak kullanılacak, kayıt değil).

Şema notu (v2.5.0 G3 ile güncellendi): Kampanya istatistiği ve regresyon-fit
kayıtlarının tür değerleri (`campaign_statistics`, `regression_correlation`)
artık doğrulayıcıda birinci sınıf `record_type` değerleridir; strand yanma-hızı
ve motor test noktası kayıtları için de `strand_burn_rate` ve
`engine_test_point` eklendi. İlgili kayıtlar artık doğru `record_type` alanını
taşır (eski kayıtlardaki bazı `notes` metinleri hâlâ "şema dışı" ifadesini
içeriyor olabilir; bu artık geçersizdir). Türlerin tam listesi ve anlamları
için `SCHEMA.md` içindeki "`record_type` değerleri" bölümüne bakın.

Sayıların alındığı ARGE denetim dosyaları:
`docs/arge-guven-2026-07/arge_hibrit_veri.md` ve
`docs/arge-guven-2026-07/arge_kati_sivi_veri.md` (date_checked: 2026-07-17).
G2 küratörlük dalgası hedefi: 8-15 kayıt (hibrit 4-6, katı 3-5, sıvı 3-4).
