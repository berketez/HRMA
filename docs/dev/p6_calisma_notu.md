# P6 çalışma notu — ana modelin 17 kalemi

Ajanlar bittikten sonra tek elden yapılacak. Sayılar ölçüldü (HYBRID_BASE
koşusu, `/calculate`), tahmin değil.

## Kök sorun: tek yanıtta üç farklı araç

| büyüklük | openrocket dalı | yörünge dalı | motorun kendi gerçeği |
|---|---|---|---|
| kuru kütle | **5,0 kg** | 50 kg | 89,27 kg (yapısal analiz) |
| çap | **0,10 m** | 0,15 m | 0,18437 m (kasa dış çapı) |
| apoje | **570.914,7 m** | 10.575,7 m | — |

Gövde çapı motor kasasından ince, kuru kütle motorun kendi yapısından 18 kat
küçük. `mass_ratio` ve `delta_v` bu 5 kg'dan türüyor.

## P6-1..5 — `app.py:1058` tek satır

Dışa aktarıcı tarafı hazır (P4 ajanı tamamladı ve ölçtü):

```python
'flight_profile': openrocket_exporter.create_flight_simulation_data(
    motor_results, rocket_params, launch_params)
```

- `launch_params` zaten `app.py:1114-1119`'da kuruluyor; ajan anahtar adlarını
  bilerek ona uydurdu (`launch_angle`, `launch_altitude`, `wind_speed`,
  `wind_direction`) — aynı sözlük iki dala birden verilebilir.
- `rocket_params` `app.py:1106-1111`'deki dörtlüden kurulur.
- Ölçülen etki (aynı motor, yalnız `rocket_params` değişti):
  `yok → apoje 570.914,7 m` | `{50 kg, 0,15 m} → 28.226,0 m` |
  `{25 kg, 0,357 m} → 85.580,6 m`

Hazır çözücüler:
- `OpenRocketExporter.resolve_inert_mass(motor_data) -> (float|None, str)`
  — ölçüldü: `(89.27, 'structural')`. **Motorun** atıl kütlesi, aracın değil →
  yalnız ALT SINIR olarak kullanılır, kaynak etiketiyle
  (`MASS_SOURCE_LABELS`).
- `OpenRocketExporter.resolve_geometry(motor_data) -> Dict`
  — `case_diameter` 0,18437 m, `case_diameter_source='chamber_plus_wall'`.

Dikkat: `_calculate_flight_performance` içinde `or 5.0` sessiz uydurması
duruyor (P4 ajanı bilerek bırakmış, o kalem P6'nın). Kaldırılırken "kullanıcı
vermedi" hâli `resolve_inert_mass` desenli kaynak etiketiyle raporlanmalı.

Ayrıca varsayılan araç sözlüğünün **dört ayrı kopyası** var
(`openrocket_integration.py:344, 831, 997, 1139`) — tek noktaya indirilmeli.

## P6-6..8 — `advanced.html` toplayıcısı

Ölçülen: `advanced.html` içinde **`vehicle_diameter` diye bir alan yok**;
toplayıcı (`:3292`) `|| 0.15`'e düşüyor. `vehicle_mass_dry` ve
`vehicle_length` de aynı durumda. Yani `trajectory` dalı tarayıcıda hiç
gerçek veri almıyor.

Sayfadaki GERÇEK alanlar (1508-1563): `initial_mass`, `final_mass`,
`drag_coefficient`, `reference_area`, `launch_angle`, `wind_speed`.

`/calculate` payload'ı `reference_area`'yı **taşımıyor** (`app.js:2306` onu
yalnız `/api/trajectory-analysis`'e koyuyor). P6-8'i `d = sqrt(4A/pi)` ile
kapatmak için önce toplayıcıya eklenmeli.

`trajectory_analysis.py:382` bağıntısı CANLI (çap 0,15 → 0,30 ile alan
0,01767 → 0,07069 m², apoje 10.575,7 → 1.581,3 m). Kusur modülde değil,
toplayıcıda.

## P6-9..11 — `/api/trajectory-analysis` (app.py:4090-4168)

İki uç birbirinin eksiğini tamamlıyor:

| konu | `/calculate` | `/api/trajectory-analysis` |
|---|---|---|
| kuru kütle | id yok → hep 50 | `final_mass` → **doğru** |
| çap | id yok → hep 0,15 | `sqrt(4A/pi)` → **doğru** |
| fırlatma açısı | istekten → **doğru** (90) | **sabit 85,0** |
| rüzgâr | istekten → **doğru** | **sabit 0,0** |
| rakım | id yok → 0 | **sabit 0,0** (istekte `trajectory_start_altitude` var, okunmuyor) |
| enlem | verilmiyor → g = g0 | **sabit 40,0** → `local_gravity(40,0)` |
| motor | gerçek `motor_results` | yoksa **thrust=1000 N, burn_time=10 s uydurma** |

Araç tarafını doğru kuran kalıp `/api/trajectory-analysis`'te, fırlatma
koşulunu doğru kuran kalıp `/calculate`'te. Karşılıklı taşınırsa iki uç da
düzelir ve iki farklı yerçekimi tek değere iner.

## İmza notları

```python
set_vehicle_parameters(mass_dry, diameter, drag_coefficient=0.5, length=2.0)
# mass_dry ve diameter ZORUNLU. None geçilirse doğrulama YOK -> TypeError.
# "Kullanıcı vermedi" demek için None GEÇME; ya değer ver ya metodu çağırma.
# app.py:1108'deki 0.15 ile kurucu:122'deki 0.15 aynı sayının İKİ KOPYASI.

set_launch_site(site: Optional[Dict])
# None/boş -> tüm alanlar varsayılana döner (regresyon kilidi).
# launch_site.resolve_launch_site(...) çıktısı sözleşmeye AYNEN uyuyor.

calculate_trajectory(motor_data, launch_params)
# motor_data'da ZORUNLU: thrust, burn_time, total_impulse, isp,
# propellant_mass_total  (.get değil -> KeyError riski)
```

## Yayın öncesi teyit edilecek (P4 ajanının açık bıraktığı)

OpenRocket XML `<launchrodangle>` **dikeyden sapma** mı, **ufuktan yükseliş**
mi? HRMA konvansiyonu 90° = dikey (`trajectory_analysis.py:12-17`). Format
konvansiyonu doğrulanmadığı için 90−θ dönüşümü YAPILMADI; şu an yazılan
değerin HRMA konvansiyonu olduğu XML yorumunda belirtiliyor. Yanlışsa 85°
"neredeyse yatay" olarak okunur.

## Partiler dışında çıkan, sahibi belirsiz iki tutarsızlık

1. `hrma/analysis/flight_vehicle.py:125 _normalize_hybrid` —
   `engine_inert_mass_note` "estimated as ~0.25 x propellant mass" diyor ama
   döndürdüğü değer 89,27 kg (0,25 × 27,47 = 6,87 olurdu). Beyan ile sayı
   çelişiyor; değer artık yapısal analizden geliyor, not güncellenmemiş.
2. Aynı fonksiyon `engine_od_m = chamber_diameter = 0,15253 m` diyor; gerçek
   kasa DIŞ çapı 0,18437 m. "OD" adlı alan iç çapı veriyor — Faz 0'da CAD
   tarafında kapatılan hatanın aynısı, bu kez launch-site köprüsünde.
