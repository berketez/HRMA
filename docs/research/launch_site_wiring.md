# Fırlatma Sahası Küresi — Bağlantı (wiring) Talimatları

Bu belge, interaktif 3B fırlatma sahası küresi + uçuş yolu animasyonu
sayfasının ana uygulamaya bağlanması için ANA OTURUMA verilen TAM YAMA
talimatıdır. Görsel katman + testler zaten hazırdır (aşağıdaki "Hazır dosyalar").
Yalnızca `hrma/app.py`'ye iki küçük ekleme ve bir gezinme bağlantısı gerekir.

Ajan `hrma/app.py`'ye YAZMADI (başka oturum sahibi). Aşağıdaki bloklar
birebir uygulanabilir; satır numaraları 2026-07-23 HEAD'ine göredir, yakın
bir bağlam eşleşmesiyle uygulayın.

---

## 1. Hazır dosyalar (uygulanacak bir şey yok — bilgi)

| Dosya | Rol |
|---|---|
| `hrma/static/js/launch_site_globe.js` | Three.js küre, Blue Marble doku, sınırlar, raycast seçim, kamera uyarlama, uçuş yolu + yer izi animasyonu, oynat/duraklat/zaman kaydıracı |
| `hrma/static/js/i18n_launch_site.js` | EN/TR sözlük (ön ek `site.`) |
| `hrma/templates/launch_site.html` | Sayfanın kendisi (koyu tema; three → OrbitControls → launch_site_globe.js sırasıyla yükler) |
| `tests/test_launch_site.py` | launch_site.py fizik testleri (18 test, hepsi geçiyor) |

`hrma/analysis/launch_site.py` DEĞİŞTİRİLMEDİ — mevcut `resolve_launch_site`
ve `enu_to_geodetic` olduğu gibi kullanılıyor. `six_dof_trajectory.py` ve
`trajectory_analysis.py` DEĞİŞTİRİLMEDİ.

---

## 2. app.py — import eklentisi

`hrma/app.py` içinde analiz importlarının olduğu bloğa (≈ satır 49-50,
`from hrma.analysis.regression_analysis import regression_analyzer` civarı)
ekleyin:

```python
from hrma.analysis.launch_site import resolve_launch_site
```

---

## 3. app.py — sayfa route'u

`/formulas` route'undan HEMEN SONRA (≈ satır 302, `return
render_template('formulas.html')`'in altına) ekleyin:

```python
@app.route('/launch-site')
def launch_site_page():
    return render_template('launch_site.html')
```

Bu route eklenince sayfa `http://<host>/launch-site` adresinde açılır.
(Ajan doğrulaması bu route'u geçici bir harness ile — `scratchpad/launch-globe/serve_test.py`
— sağladı; kalıcı hâli budur.)

---

## 4. app.py — saha çözümleyici endpoint'i

6-DOF endpoint'inin (≈ satır 968-1044, `six_dof_analysis`) hemen ARDINA,
`# ------ Dalga 3 ...` yorum bloğundan ÖNCE ekleyin:

```python
@app.route('/api/launch-site/resolve', methods=['POST'])
def launch_site_resolve():
    """Konumdan tam saha tanımı: rakım (DEM) + yerel g (WGS84) + yüzey atmosfer.

    Girdi (JSON): latitude, longitude [zorunlu]; elevation_m, temperature_k,
    pressure_pa [ops. elle datum]; use_online [ops. bool, Open-Meteo].
    Çıktı: hrma.analysis.launch_site.resolve_launch_site() sözlüğü.

    KRİTİK: gravity_local_m_s2 enlem+rakımla değişir ama gravity_standard_m_s2
    her zaman 9.80665'tir (Isp/ideal-dV zinciri buna dokunmaz).
    """
    try:
        data = request.json or {}
        if data.get('latitude') is None or data.get('longitude') is None:
            return jsonify({'status': 'error',
                            'error': 'latitude and longitude are required'}), 400
        site = resolve_launch_site(
            float(data['latitude']), float(data['longitude']),
            elevation_m=(float(data['elevation_m'])
                         if data.get('elevation_m') not in (None, '') else None),
            temperature_k=(float(data['temperature_k'])
                           if data.get('temperature_k') not in (None, '') else None),
            pressure_pa=(float(data['pressure_pa'])
                         if data.get('pressure_pa') not in (None, '') else None),
            use_online=bool(data.get('use_online', False)),
        )
        return jsonify(sanitize_json_values({'status': 'success', 'site': site}))
    except (TypeError, ValueError) as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500
```

`sanitize_json_values` ve `traceback` app.py'de zaten mevcut (six-dof
endpoint'i ikisini de kullanıyor). Sayfanın sol panelindeki "Sahayı çöz"
düğmesi bu endpoint'i çağırır; endpoint yoksa panel zarifçe
"çözümleyici ucu henüz bağlanmadı" der (yani bu adım OPSİYONEL ama saha
rakımı/yerçekimi göstergesi için gereklidir).

---

## 5. Uçuş yolu verisi — sunucu değişikliği GEREKMEZ

Sayfa uçuş yolunu MEVCUT `/api/six-dof-analysis` endpoint'inden alır. O
endpoint `series` içinde `north`, `east`, `altitude` (yerel ENU, metre)
döndürür; küre bunları istemci tarafında `enu_to_geodetic`'in JS kopyasıyla
(launch_site_globe.js) enlem/boylam/rakıma çevirir. Bu, launch_site.py'deki
`enu_to_geodetic` ile BİREBİR aynı birinci-mertebe teğet-düzlem formülüdür
(tests/test_launch_site.py Python tarafını kilitler).

İSTEĞE BAĞLI iyileştirme (gerekli değil): six-dof endpoint'i yanıtına
sunucu tarafında hesaplanmış `series.latitude`/`series.longitude` eklenmek
istenirse, `hrma/app.py` six_dof_analysis içinde `series` sözlüğü kurulduktan
sonra (≈ satır 1032) ve girdiye `launch_latitude`/`launch_longitude`
eklenerek yapılabilir:

```python
        # (İSTEĞE BAĞLI) jeodezik yer izi sunucudan:
        lat0 = data.get('launch_latitude'); lon0 = data.get('launch_longitude')
        if lat0 is not None and lon0 is not None:
            from hrma.analysis.launch_site import enu_to_geodetic
            glat, glon, galt = enu_to_geodetic(
                float(lat0), float(lon0), 0.0,
                res['position'][0][idx], res['position'][1][idx],
                res['altitude'][idx])
            series['latitude'] = glat.tolist()
            series['longitude'] = glon.tolist()
```

Yapılırsa küre JS'i istemci dönüşümü yerine bu alanları tercih edecek
şekilde küçük bir dallanma alabilir; ama MEVCUT hâliyle istemci dönüşümü
yeterli ve testlidir. Bu adım atlanabilir.

---

## 6. Gezinme bağlantısı (index.html — ajan bu dosyayı DÜZENLEMEDİ)

Ana sayfadaki (veya alt sayfaların gezinme şeridindeki) bağlantı listesine
"Fırlatma Sahası" bağlantısı eklenmesi önerilir. `hrma/templates/index.html`
içinde diğer sayfa bağlantılarının (`/solid`, `/liquid`, `/hybrid`,
`/formulas`) bulunduğu yere, aynı kalıpla:

```html
<a href="/launch-site" data-i18n="nav.launchSite">Launch Site &amp; Flight Path</a>
```

`nav.launchSite` anahtarı i18n_pages.js'e (ana sayfa sözlüğü) eklenebilir
(EN: "Launch Site & Flight Path", TR: "Fırlatma Sahası ve Uçuş Yolu").
Bağlantı stili mevcut gezinme bağlantılarıyla aynı olmalı. Bu bir kolaylık
adımıdır; sayfa route eklenince doğrudan URL ile de erişilebilir.

---

## 7. Doğrulama (uygulandıktan sonra)

```bash
python3 -m pytest tests/test_launch_site.py -q          # 18 test geçer
python3 -m pytest tests/test_i18n.py -q                 # i18n sözleşmesi
python3 -m pytest tests/ -q -k "trajectory or sixdof or launch"   # regresyon
node --check hrma/static/js/launch_site_globe.js
node --check hrma/static/js/i18n_launch_site.js
```

Tarayıcıda: `/launch-site` aç → küre çizilmeli (Blue Marble + sınırlar),
küreye tıkla → sol panelde enlem/boylam güncellenir, "Sahayı çöz" → rakım +
yerel g + standart g0 ayrı ayrı görünür, "Bu sahadan uçur" → 6-DOF uçuş yolu
küre üzerinde çizilir ve oynatılır. Konsol hatası SIFIR olmalı.

---

## 8. Notlar / dürüstlük sözleşmesi (korunmalı)

- Yer izi "Dünya dönüşü MODELLENMEDİ" diye etiketlidir; Dünya dönüşü/Coriolis
  v1'de fiziğe bağlı değildir (launch_site.NOT_MODELLED).
- Ölçek varsayılan GERÇEKTİR; "Rakımı abart" anahtarı yalnız okunabilirlik
  içindir, varsayılan KAPALIDIR ve etiketlidir.
- Yakın zoomda küresel doku/DEM (~9 km) yerel arazi detayı içermez; sahte
  arazi ÜRETİLMEZ, kullanıcı bir notla uyarılır (zoom sınırı + not yaklaşımı
  seçildi).
- Yerel g YALNIZ ağırlık/yörünge/T-W'ye girer; Isp ve ideal delta-v
  g0=9.80665'te kalır (launch_site.py bunu kilitler, endpoint bozmaz).
```
