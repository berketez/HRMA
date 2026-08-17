# Bebek-Scofield — ön tarama bulgu sicili (17 Ağustos 2026)

> **DURUM: 25/25 KAPANDI** (aynı gün, parti 31 — 6 ajan, kesişmeyen dosya
> kümeleri). Kapanışların bekçileri ve öncesi/sonrası sayıları
> `BULGU_KAYIT_DEFTERI.md` v2.6.27 tablosundadır. Bu dosya **ölçüm geçmişi**
> olarak durur: aşağıdaki "öncesi" sayıları kusurun gerçekten var olduğunun
> kaydıdır ve bir daha üretilirse karşılaştırma tabanıdır. Yapılacaklar
> listesi DEĞİLDİR.

**Ne bu:** Operasyon Scofield'ın (yol haritası §3.5) *öncesinde*, Berke'nin
isteğiyle yapılmış örneklem tabanlı ön tarama. Scofield'ın **yerine geçmez**;
Scofield tüm iş kalemleri bittikten sonra, hiçbir hücre atlanmadan yapılır.

**Nasıl ölçüldü:** 11 ajan — 5 ürün bulucusu (hibrit / katı / sıvı fizik,
çapraz tutarlılık, dürüstlük) + 2 hakem; 3 bekçi denetçisi (kusuru kilitleyen,
ısırmayan, sessiz atlama) + 1 hakem. Bulucular salt-okur çalıştı; mutasyon
denetçisi ayrı git worktree'de. Hakemlerin varsayılanı "çürütüldü" idi: bir
iddia ancak hakem kendi koşturup aynı sayıyı aldığında ayakta kaldı.

**Sonuç:** ürün 22 ham → **18 doğrulandı**; bekçi 9 ham → **7 doğrulandı**
(2'si hükümsüz kaldı, ana model doğruladı). 1 kritik.

Baskın sınıf defterin kendi tezini doğruluyor: *iki parça tek başına doğru,
aralarındaki sözleşme yanlış.*

---

## A — Aynı büyüklük, aynı yanıtta iki değer

| # | Şiddet | Ölçülen çelişki | Yer |
|---|---|---|---|
| F5-1 | **kritik** | Isı zinciri cidarı **5,0 mm** ⟷ yapısal/CAD **18,79 mm**; ürün yine de `safety_factor_at_drawn_wall = 2,152` yayımlıyor (ısı zincirinin görmediği cidar için). CAD dış çapı 157,62 mm aynı kalınlıktan türüyor. | `hybrid_rocket_engine.py:965-977` (sessiz 0,005 m varsayılanı), `:1802` |
| F5-4 | yüksek | Aynı kanal devresi: tepe akı **52,15 ⟷ 10,95 MW/m²** (4,76×), soğutucu çıkışı **820,0 ⟷ 421,9 K** | `liquid_rocket_engine.py:9678-9690` ⟷ `:9700-9738` |
| F5-3 | yüksek | Aynı turbopompa iki kez: türbin gücü **169,55 ⟷ 110,21 kW** (kullanıcıya gösterilen büyük olan) | sıvı motor yanıtı |
| F3-1 | orta | C_D=0,98 boğaz alanına gömülü, iki seri geri okumuyor: t=0 itki **3000,0 ⟷ 3061,2 N**, oda basıncı **30,00 ⟷ 29,40 bar**. Şişme `isp_delivered_avg` ve `total_impulse`'a geçiyor. | `hybrid_rocket_engine.py:2754`, `transient_ballistics.py:567` ⟷ `:519-520` |
| F1-1 | yüksek | Sıvı açık çevrim muhasebesi ölü kod: başlık sayıları kendi yakınsamış çevrim çözümüyle çelişiyor | `_apply_cycle*` |
| F1-3 | orta | Aynı enjektör manifolduna beyansız 2,5×d kaba kuralıyla ikinci çap (fuel 23,58 / ox 32,83 mm) | `injector_design` bloğu |
| F2-1 | yüksek | Katı kasa tek kapta iki malzeme kimliği (akma/cidar 250 MPa "jenerik çelik", patlama başka) | katı yapısal zincir |
| F5-2 | yüksek | Yapısal panel cidar sıcaklığı devrini (`wall_temperature_hot/cold`) hiç göndermiyor; güverte ayrı SF (4,3132) / 728,9 K gösteriyor | analiz güvertesi |

## B — Sessiz varsayılan, uydurma sabit

| # | Şiddet | Ölçülen | Yer |
|---|---|---|---|
| F4-3 | yüksek | `thrust=0` → sessizce **F=1000 N**, üstelik `supplied=['thrust']`. Deponun kendi `utils/input_guard.py:9-12` dosyası bu kuralı ilke olarak yazıyor ve **örnek olarak tam bu hatayı** veriyor. | `hybrid_rocket_engine.py:609-610` |
| F4-1 | yüksek | Boş girdiyle 155 yaprağın tamamı doluyor: `heat_flux = 13,03 MW/m²`, `risk_level = HIGH`; boş↔dolu farklı yaprak sayısı **0**. Kardeş uçlar aynı durumda 422 dönüyor. | `heat_transfer_analysis.py:653-654` (beyan) ⟷ `:676-681` (davranış) |
| F5-5 | orta | Motorun yayımlamadığı `turbopump.reliability` okunuyor → ekranda `Reliability: NaN%` | sıvı sayfası kartı |

## C — Yanlış yönlü ya da dayanaksız hüküm

| # | Şiddet | Ölçülen | Yer |
|---|---|---|---|
| F1-2 | yüksek | Tank basıncı marjı **+4,40 bar** yayımlanıyor; aynı yanıtta çevrim çözücüsü **−3,58 bar** + `warn.cycle.pressure_fed_infeasible` / `severity: critical`. 95 bar tank, 98,58 bar yakıt gereksinimi. Tek kaynak `cycle_power_balance.py:613`'te mevcut. | `liquid_rocket_engine.py:8006` |
| F4-2 | yüksek | Yapısal emniyet hükmü, modülün kendisinin "totolojik" diye işaretlediği SF'den türüyor | yapısal zincir |

## D — Girdi kapısı yok

| # | Şiddet | Ölçülen |
|---|---|---|
| F4-4 | orta | Çalkalanma çözücüsünde pozitiflik kapısı yok: negatif yoğunluk 200 ile geçiyor, **negatif sıvı kütlesi** yayımlanıyor |
| F4-5 | orta | `of_ratio = −6` tam bir performans sonucu üretiyor (negatif eşdeğerlik oranı dâhil) |

## E — Ad ile davranış ayrışması

| # | Şiddet | Ölçülen |
|---|---|---|
| F3-2 | yüksek | `total_mass_kg` yanan yakıtla toplanıyor: **97,23 ⟷ 102,48 kg** (%5,1 / 5,25 kg sliver). Aynı yanıtın `oxidizer_mass_basis` alanı kuralı zaten yazıyor ("kütle bütçesi yüklenen değeri kullanmalı") |
| F3-3 | orta | `vacuum_isp` gerçek vakum değil, irtifa tablosunun 20 km satırı: **268,13 ⟷ 269,62 s**. Doğrusu aynı fonksiyonun `thrust_vacuum_n` alanında zaten var |
| F2-2 | orta | Katı `isp_vacuum` ampirik log-fit çarpanı P_c'yi hiç görmüyor → yanıtın kendi C_F fiziğiyle ~**%7** çelişiyor |

**Çürüyen (1):** F2-3 eğri örnekleme `max_points=400` iken `points_published=402` —
hakem haklı, blok davranışı (`zorunlu indeksler eklenir, kırpma yok`) kendi
basis metninde beyanlı. En fazla adlandırma kalemi.
**Hükümsüz (3):** F3-4/F3-5/F3-6, hepsi düşük şiddet.

---

## Bekçi denetimi (testlerin kendisi)

| # | Şiddet | Ölçülen |
|---|---|---|
| T2-1 | yüksek | **17 bekçi CI'da hiçbir yerde koşmuyor.** `build123d` gizlenerek ölçüldü: `test_step_durustluk_kapisi.py` + `test_faz5_cizim_birim.py` → **30 passed / 17 skipped**; bağımlılık açıkken **47 passed**. Ana işte atlama envanteri *bilgi amaçlı*; ayrı `step-export` işi fail-closed ve atlama bütçesi sıfır ama **elle yazılmış 5 dosyalık listeyle** koşuyor ve bu iki dosya ne o listede ne `release.yml`'de. 2026-08-03'te kapatılan node deliğinin aynı sınıfı: çözüm doğruydu, **listesi çürüdü**. |
| T2-2 | yüksek | Cantera denge yolu **üründe** bozulursa (mekanizma zinciri mutasyonuyla ölçüldü) onu koruyan 39 bekçi "Cantera kurulu değil" gerekçesiyle atlıyor — hiçbiri kırmızıya dönmüyor |
| T2-3 | yüksek | CoolProp gerçek-gaz yolunda aynı desen, 5 bekçi |
| T2-4 | düşük | numba↔NumPy bit-özdeşliğini kanıtlayan tek bekçi CI'da hiç çalışamaz — **numba hiçbir requirements/iş akışı dosyasında yok** (ana model doğruladı) |
| T1-1 | orta | NaN bekçisi totolojik: `assert 'nan' not in flat.lower() or 'NaN' not in flat`. Python NaN'ı daima küçük harf yazar → sağ taraf daima doğru, OR koşulsuz geçer. Tüm sayısal yaprakları NaN yapan mutasyonla ölçüldü: **1 passed** |
| T3-1 | orta | TM-107041 10× bant bekçisi **tek yönlü**: tarihi kusurun kendisi (tablo çarpanının unutulması) geri geldiğinde 48/48 yeşil |
| T3-2 | orta | SF totoloji bekçisi etiket/imza kontrolüyle yetiniyor: verify-modu SF'si kullanıcı cidarının basınç teriminden koparılınca adlı bekçi ve dosyası **30/30 yeşil** |
| T1-2 | düşük | Doğrulama süiti APCP referansı **22,00 ⟷ 9,83 mm/s** (2,24×, katalog tek kaynağına göre) ve "typical APCP" etiketli; ürün aynı girdiye `burn_rate_off_catalog` uyarısı basıyor, test uyarıyı hiç görmüyor. Bilinen MPa↔bar karışımının (F024) doğrulama süitindeki ayağı |
| T1-3 | düşük | RS-25 boğaz akısı: docstring ve hata mesajı **80-160 MW/m²** derken kapı **80-200**; 161-200 arası sessiz geçer (bugünkü değer 131,4 — genişletme şu an yük taşımıyor) |

### Denetimin olumlu ölçümleri

- Atıf denetimi: seçilen **8** literatür iddiasının **8**'i bağımsız hesapla tuttu
  (Sutton λ(15°)=0,983; ISO 898-1 diş alanları M8 36,61 / M10 57,99 mm²;
  USSA-1976 25 km noktası; WGS84 Somigliana uçları; kritik basınç oranı 0,5283;
  C_F el çapası 1,2578).
- **907** literal `pytest.approx` deseni sayıldı, **120+**'si tek tek "kaynağı ne?"
  sorusuyla incelendi; büyük çoğunluğu analitik el hesabı, künyeli literatür
  değeri ya da açıkça beyanlı anlık görüntü çıktı.
- Kapsam içinde **xpass yok**; tek xfail beyanlı ve `strict=True`.

---

## Kapanış kuralı

Bu dosya bir yapılacaklar listesi değil, **ölçüm kaydıdır**. Defterin kuralı
aynen geçerli: bir bulgu ancak **kusurun kendisini yakalayan bir bekçiye**
bağlandığında kapanır; kapanmayan gerekçesiyle `BULGU_KAYIT_DEFTERI.md` açık
borç listesinde durur. Kod okunarak varılan kanaat yeterli değildir.

**Süreç notu (ölçüldü):** "salt-okur" diye görevlendirilen bulucu ajanlardan
bazıları üretim dosyalarını geçici mutasyona uğratıp geri aldı
(`update_checker.py`, `pressurant_sizing.py`, `combustion_analysis.py` — üçünün
de md5'i HEAD ile birebir aynı kaldı, hasar yok). Sonraki dalgalarda salt-okur
bulucular ya worktree'ye alınmalı ya da ana ağaçta HEAD'den sapma tel-tuzağı
kurulmalı (bu turda kuruldu).
