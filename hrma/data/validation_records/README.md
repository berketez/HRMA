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

Sayıların alındığı ARGE denetim dosyaları:
`docs/arge-guven-2026-07/arge_hibrit_veri.md` ve
`docs/arge-guven-2026-07/arge_kati_sivi_veri.md` (date_checked: 2026-07-17).
G2 küratörlük dalgası hedefi: 8-15 kayıt (hibrit 4-6, katı 3-5, sıvı 3-4).
