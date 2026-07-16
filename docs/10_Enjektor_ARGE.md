# Enjektör Tasarımı ARGE Raporu ve `injector_design.py` API Sözleşmesi

**Tarih:** 2026-07-13 · **Durum:** İmplementasyon sözleşmesi (TEK gerçek kaynak)
**Hedef:** HRMA'ya "adam akıllı" enjektör tasarım kapasitesi — hibrit (yalnız
oksitleyici) ve sıvı (çift yakıt) motorlar için. Kullanıcı kitlesi amatör/
üniversite ölçeği (Uzaytek): N₂O hibrit + küçük LOX/RP-1 veya N₂O/etanol sıvı.

---

## 0. Mevcut Durum (neden yetersiz)

| Yer | Mevcut model | Eksik |
|---|---|---|
| `liquid_rocket_engine.py` ~950-1070 | SPI: ΔP=%15-28·Pc, v=Cd·√(2ΔP/ρ), A=ṁ/(ρv); Weber tabanlı damlacık (gaz yoğunluğuna yeni düzeltildi) | Tip seçimi yok, patern yok, SMD korelasyonu kaba (|v_ox−v_f| eş hızlarda çöküyor), Rupe/momentum kriteri yok, manifold yok, kavitasyon/flip yok |
| `hybrid_rocket_engine.py` ~561-880 | Sabit 'showerhead', n=12 sabit, tek ΔP, tek-faz SPI | N₂O iki-faz akış (kritik!), tip seçenekleri, delik planı optimizasyonu, kararlılık kontrolü yok |
| `advanced.html` injector_config | injection_velocity + pressure_drop_percent girdisi | Tasarım çıktısı yok, yalnız iki skaler |

En kritik fiziksel eksik: **kendinden basınçlı N₂O doyma noktasında akar** —
tek-fazlı SPI, orifiste flaşlamayı (iki-faz boğulma) görmez ve debiyi
sistematik olarak **fazla** tahmin eder (%15-40'a varan hata; Waxman 2013).

---

## A. ARGE BÖLÜMÜ

### A.1 Enjektör tipleri ve seçim matrisi

| Tip | Çalışma ilkesi | Uygulama | Avantaj | Dezavantaj | Amatör üretilebilirlik |
|---|---|---|---|---|---|
| **Showerhead** (düz delikli) | Eksenel paralel jetler | Hibrit oksitleyici, gaz jeneratörü | En basit imalat (matkap), tıkanmaya dayanıklı | Atomizasyon zayıf (yalnız jet parçalanması), karışım yok | 5/5 |
| **Unlike-impinging doublet** (O-F çarpışan) | Farklı akışkan jetleri 2θ≈60° ile çarpışır | Küçük sıvı motorlar (depolanabilir/RP-1) | İyi karışım + atomizasyon, basit | Momentum dengesine duyarlı, ısı akısı çizgileri (fan düzlemi), blowapart riski | 4/5 |
| **Like-impinging doublet/triplet** (F-F, O-O) | Aynı akışkan kendi içinde çarpışır | Hipergolik, kararlılık istenen tasarımlar | Blowapart yok, duvara yakın yakıt filmi kolay | Karışım fana kalır (biraz daha düşük η) | 4/5 |
| **Unlike triplet (O-F-O)** | 2 dış jet ortadakine simetrik çarpar | O/F>2 sıvılar | Momentum simetrisi doğal, iyi karışım | Delik hizalama hassasiyeti | 3/5 |
| **Pintle** | Merkez iğne: radyal iç akış + anülüs dış akış çarpışır | Derin kısılabilir motorlar (TRW/Merlin mirası) | Tek elemanla kısılabilirlik, doğal kararlılık geçmişi, az delik | Tek nokta ısı yükü, tasarım bilgisi TMR/BF'e gömülü | 3/5 (torna yeter) |
| **Koaksiyel shear** | Merkez sıvı + anülüs gaz kesme | Gaz-sıvı (LOX/GH₂) | Kriyojenik mirası | Gaz fazı şart; amatör sıvı-sıvıda etkisiz | 2/5 |
| **Koaksiyel/basınç swirl** | Teğetsel girişle döndürülen film konisi | Sıvı-sıvı, N₂O hibrit (vorteks) | Mükemmel atomizasyon (ince film), ΔP'ye görece tolerant | İmalat hassasiyeti (teğet kanallar), analiz karmaşık | 3/5 (CNC ile) |
| **Vorteks/swirl (hibrit N₂O)** | Oksitleyici teğetsel girişle port üstünde döner | N₂O hibrit özel | Regresyon ↑ (%'lerle ölçülü artış), yanma verimi ↑, film etkisi | Swirl sönümü, veri amatör literatürde sınırlı | 4/5 |

**Seçim kuralları (varsayılanlar):**
- Hibrit N₂O → `showerhead` (varsayılan) veya `swirl` (vorteks); iki-faz model **zorunlu**.
- Sıvı depolanabilir/RP-1 → `impinging_doublet` (varsayılan), O/F ≥ 2.5'te `impinging_triplet` düşün.
- Kısılabilirlik istenirse → `pintle`.
- Atomizasyon önceliğiyse (küçük ölçek, düşük ΔP) → `coax_swirl` / `swirl`.

### A.2 Orifis akışı ve boşaltım katsayısı

Temel bağıntı (tüm tipler, sıkıştırılamaz tek faz — **SPI**):

```
ṁ = Cd · A · √(2 · ρ · ΔP)          [kg/s; A m², ρ kg/m³, ΔP Pa]
v  = Cd · √(2 · ΔP / ρ)             [m/s — efektif enjeksiyon hızı]
A  = ṁ / (ρ · v)                    [tutarlılık özdeşliği]
```
Kaynak: Sutton & Biblarz 9. baskı Böl. 8; NASA SP-8089 (Liquid Rocket Engine
Injectors, 1976).

**Cd seçim tablosu** (SP-8089 + Lefebvre & McDonell 2. baskı Böl. 5):

| Orifis geometrisi | L/D | Cd | Not |
|---|---|---|---|
| Keskin kenar, kısa | < 1 | 0.61-0.65 | Vena contracta hakim |
| Keskin kenar, yeniden yapışan | 2-5 | 0.75-0.85 | **Hydraulic flip riski** bu bantta |
| Keskin kenar, uzun | 5-10 | 0.80-0.88 | Sürtünme artar |
| Radüslü giriş (r/d ≥ 0.15) | 2-5 | 0.88-0.95 | Önerilen: kararlı Cd |

**Kavitasyon / hydraulic flip:** Kavitasyon sayısı
`K_c = (P₁ − P_v) / (P₁ − P₂)`. K_c küçüldükçe (≲ 1.2-1.5, keskin girişte)
vena contracta buharla dolar; akış orifis duvarından ayrılıp "flip" yapar →
Cd aniden ~0.61'e düşer, sprey daralır. Kural: **keskin giriş + L/D 2-5 +
K_c < 1.5 → flip riski bayrağı**; çözüm radüslü giriş veya L/D ≥ 5.
(Kaynak: Nurick 1976, ASME J. Fluids Eng.; Lefebvre & McDonell Böl. 5.)

### A.3 N₂O kendinden basınçlı iki-faz akış — model seçimi

| Model | Formül | Davranış |
|---|---|---|
| **SPI** | `ṁ = Cd·A·√(2ρ_l·ΔP)` | Flaşlamayı görmez → doyma yakınında **fazla** tahmin |
| **HEM** (homojen denge) | `ṁ = Cd·A·ρ₂·√(2(h₁−h₂))`, izentropik (s₂=s₁) çıkış hâli, boğulma: G maksimumu | Kabarcık büyümesine sonsuz zaman varsayar → kısa orifiste **eksik** tahmin |
| **Dyer NHNE** (önerilen) | `ṁ = (κ·ṁ_SPI + ṁ_HEM) / (1+κ)`, `κ = √((P₁−P₂)/(P_v−P₂))` | Kalış süresi/kabarcık süresi oranını κ ile tartar; doymuş girişte κ=1 → aritmetik ortalama; aşırı soğutulmuş girişte κ→∞ → SPI'a yakınsar |

**Karar: hibrit N₂O yolu için Dyer NHNE.** Deneysel doğrulama ±%15
(Dyer/Doran/Dunn/Zilliac AIAA 2007-5702; Solomon 2011, Utah State;
Waxman ve ark. 2013 Stanford; Zimmerman ve ark.). HEM tek başına boğulmuş
debiyi ~%15-40 eksik, SPI doyma yakınında fazla verir. NHNE'nin boğulma
sınırını temsil etmediği durum uyarı olarak raporlanır (`warnings_tr`).

N₂O doyma özellikleri: mevcut `tank_blowdown.py` N₂O tablosundan alınır
(P_sat(293 K) ≈ 50.4 bar — 2026-07-13 formül teyidinde doğrulandı);
h, s, ρ doyma eğrisi interpolasyonu oradaki tabloyla paylaşılır.

### A.4 Atomizasyon — SMD korelasyonları

Ortam gazı yoğunluğu her korelasyonda **oda gazı**dır:
`ρ_A = (P_c·10⁵) / ((R_u/MW)·T_c)` (2026-07-13 Weber düzeltmesiyle tutarlı).

1. **Düz orifis / showerhead** — Elkotb (1982):
   `SMD = 3.08 · ν_l^0.385 · (σ·ρ_l)^0.737 · ρ_A^0.06 · ΔP^(−0.54)`  [SI → m]
   (ν_l m²/s, σ N/m, ρ kg/m³, ΔP Pa). Dizel düz jet verisinden; showerhead
   için birinci mertebe.
2. **Basınç-swirl** — Lefebvre (1983; Lefebvre & McDonell 2. baskı):
   `SMD = 2.25 · σ^0.25 · μ_l^0.25 · ṁ_l^0.25 · ΔP^(−0.5) · ρ_A^(−0.25)`  [SI → m]
3. **Impinging (doublet/triplet)** — çarpma-dalga rejimi eğilimi:
   `D₃₂ = C_imp · d_j · We_j^(−1/3)`, `We_j = ρ_l·v_j²·d_j/σ`
   `C_imp` varsayılan **2.6** (kalibrasyon bandı 2-4; Ingebo NACA TN 3265
   D₃₀ verisi ve impact-wave çalışmalarıyla uyumlu eğilim — sabit, test
   verisiyle kalibre edilebilir alan olarak raporlanır).
4. **Pintle** — birincil kırılım TMR'ye gömülü; SMD için (3) çarpışan
   tabaka yaklaşımı, `v_j` yerine bileşke hız.

Sprey yarı koni açısı (swirl): Giffen–Muraszew inviscid teorisi (A.6).

### A.5 Impinging tasarım kuralları

- **Unlike doublet momentum dengesi:** hedef `MR = (ṁ·v)_f / (ṁ·v)_ox ≈ 1`
  → bileşke fan eksene paralel. Pratik bant 0.7-1.3.
- **Rupe karışım kriteri** (Rupe, JPL 1953): en iyi karışım
  `R_rupe = (ρ_f·v_f²·d_f) / (ρ_ox·v_ox²·d_ox) ≈ 1` civarında (bant 0.7-1.3).
- **Unlike triplet (O-F-O):** dış jet momentumları simetrik; efektif
  `TMR_triplet = 2·(ṁv)_dış·sin(θ) / (ṁv)_orta` ile eksenel bileşke korunur.
- **Çarpışma yarı açısı:** 20-40° (2θ = 40-80°; tipik 2θ=60°) — SP-8089.
- **Serbest jet boyu (impingement mesafesi):** `L_imp = 5-7·d_j`
  (jet kararsızlaşmadan çarpışmalı) — SP-8089.
- **Delik aralığı:** eleman merkezleri ≥ 3·d (jet bağımsızlığı).
- **Blowapart (hipergolik/reaktif):** unlike çarpışmada gaz üretimi jetleri
  ayırabilir; N₂O/hidrokarbon sıvıda düşük risk, uyarı notu yeter.

### A.6 Pintle tasarım kuralları

Tanımlar (Casiano/Hulka/Yang JPP 2010 derlemesi; Cheng ve ark. 2017 Acta
Astronautica; Dressler & Bauer AIAA 2000-3871):

- **TMR** `= (ṁ·v)_radyal / (ṁ·v)_eksenel` (iç radyal jetler / dış anülüs).
  Sprey yarı açısı momentum dengesinden: `θ ≈ arccos(1/(1+TMR))`
  (Cheng 2017 momentum modeli; deneysel bant: TMR 0.36-2.76 → θ 26-80°).
  **Hedef TMR ≈ 1** → θ ≈ 60° (yanma verimi maksimumu civarı).
- **Blockage Factor** `BF = n·d_o / (π·D_p)` (radyal deliklerin pintle
  çevresini kapatma oranı). TRW mirası bant **0.3-0.74**, tatlı nokta ~0.58.
- **Skip distance** `L_s / D_p ≈ 1` (0.7-1.0 tasarım bandı; deneyde en iyi
  yanma verimi ≈1'de).
- Anülüs boşluğu: `t_ann = √(D_iç² + 4·A_ann/π) − D_iç)/2` ≥ 0.3 mm imalat.

### A.7 Swirl (basınç-swirl / vorteks) tasarım kuralları

Giffen & Muraszew (1953) inviscid teorisi (Lefebvre & McDonell Böl. 5):

- Atomizör sabiti: `K = A_p / (π · r_s · r_o)` (A_p teğet giriş toplam alanı,
  r_s swirl odası yarıçapı, r_o çıkış orifis yarıçapı).
- Hava çekirdeği alan oranı X (`= A_hava/A_orifis`), maksimum debi ilkesiyle
  K'den çözülür: `K = √(32/π²) · √((1−X)³/X²)` (implementasyonda X için
  0<X<1 kök araması).
- Boşaltım katsayısı: `Cd = √((1−X)³ / (1+X))` (tipik 0.2-0.45 — düz
  orifisten belirgin düşük olması FİZİKSELDİR).
- Sprey yarı açısı: `sin θ = (π/2)·Cd / (K·(1+√X))` (tipik 2θ = 60-120°).
- Film kalınlığı (çıkışta): `t_film = r_o·(1−√X)`.
- Hibrit vorteks enjeksiyonda aynı makine oksitleyici portu üstüne uygulanır;
  swirl sayısı `S = (π·r_o·R_giriş)/A_p` raporlanır.

### A.8 Manifold tasarımı

- **Hız oranı kuralı:** manifold çapraz akış hızı / orifis hızı ≤ **0.1**
  (ideal, ≲%2 debi sapması); 0.2'ye kadar kabul edilebilir (uyarıyla).
- **Alan kuralı:** manifold kesiti ≥ **4×** beslediği orifis toplam alanı
  (Huzel & Huang Böl. 4 pratiği).
- Dome/manifold hacmi büyüdükçe chug'a karşı kapasitans artar ama tepki
  gecikir; amatör ölçekte kural: hacim ≈ 1-3 sn'lik debi hacmi ile sınırla.

### A.9 Kararlılık kuralları

1. **Chug (düşük frekans):** enjektör direnci besleme-oda kuplajını kırar.
   Kural: **ΔP_inj/P_c ≥ 0.15-0.20** (NASA SP-8089; Sutton Böl. 9). <0.15
   → `chug_ok=False` + uyarı; kısılabilir tasarımda en derin kısma
   noktasında da sağlanmalı.
2. **N₂O besleme kuplajı (hibrit):** kendinden basınçlı N₂O'da tank-besleme
   dinamiği + iki-faz enjektör debi eğrisi kuplaja girebilir; boğulmuş
   (choked) iki-faz orifis akışı **akustik izolasyon** sağlar (NASA NTRS
   20190001326). Kural: doymuş girişte ΔP/P_c ≥ 0.20 öner + "orifis
   boğulması izolasyon sağlar" bilgisi; ΔP çok düşükse feed-coupling uyarısı.
3. **Akustik (yüksek frekans):** eleman deseni teğetsel modları besleyebilir;
   amatör ölçekte tasarım kuralı vermek yerine uyarı metni: baffle/kavite
   analizi kapsam dışı, Pc>50 bar + F>5 kN tasarımlarda literatüre bak.

### A.10 Doğrulama örnekleri (spot-check, elle hesaplanmış)

**Ö1 — SPI kapalı form (su, soğuk akış):**
ρ=998 kg/m³, ΔP=10 bar, Cd=0.65, n=8, d=1.0 mm →
A_tek=7.854·10⁻⁷ m², √(2ρΔP)=44 677 →
**ṁ = 0.65·8·7.854e-7·44677 = 0.1825 kg/s**, v = 29.1 m/s.
(ṁ=ρ·A_top·v özdeşliği: 998·6.283e-6·29.1 = 0.1825 OK)

**Ö2 — N₂O NHNE (hibrit, doymuş giriş):**
T=293.15 K → P₁=P_v=50.4 bar, ρ_l≈770 kg/m³; P_c=30 bar → ΔP=20.4 bar.
κ = √((50.4−30)/(50.4−30)) = **1** → ṁ = (ṁ_SPI+ṁ_HEM)/2.
Tek orifis d=1.5 mm, Cd=0.66: ṁ_SPI = 0.66·1.767e-6·√(2·770·20.4e5)
= 0.0654 kg/s. HEM (izentropik, N₂O tablosundan) tipik olarak SPI'ın
~0.6-0.8'i → temsili ṁ_HEM=0.70·SPI=0.0458 → **ṁ_NHNE ≈ 0.0556 kg/s**
(SPI'dan %15 düşük — SPI kullanmanın hatası budur).
Assert edilecek sıralama: **ṁ_HEM < ṁ_NHNE < ṁ_SPI** (doymuş girişte).

**Ö3 — Unlike doublet + Rupe (LOX/RP-1):**
ṁ_ox=1.20, ṁ_f=0.50 kg/s (O/F 2.4), P_c=20 bar, ΔP=4 bar (her iki devre),
Cd=0.75, ρ_ox=1141, ρ_f=810 →
v_ox=19.9 m/s, v_f=23.6 m/s; n=16/16 → d_ox=2.05 mm, d_f=1.44 mm.
MR=(0.5·23.6)/(1.2·19.9)=**0.49** (hedef 1'in altında → uyarı + öneri:
yakıt ΔP'sini artır veya delik planını değiştir).
R_rupe=(810·23.6²·1.44e-3)/(1141·19.9²·2.05e-3)=**0.70** (bandın kenarı).
Bu örnek testte "uyarı üretmeli" senaryosudur.

---

## B. `hrma/engines/injector_design.py` API SÖZLEŞMESİ

Tek genel giriş noktası:

```python
def design_injector(spec: dict) -> dict
```

Yardımcılar (test edilebilir, saf fonksiyonlar — dışa açık):

```python
def spi_mass_flow(cd, area_m2, rho, dp_pa) -> float          # kg/s
def hem_mass_flow(cd, area_m2, fluid_state) -> float          # kg/s (N₂O tablosu)
def nhne_mass_flow(cd, area_m2, p1_bar, p2_bar, pv_bar, ...) -> dict
def discharge_coefficient(inlet: str, l_over_d: float) -> tuple[float, str]
def smd_elkotb(...) -> float; def smd_lefebvre_swirl(...) -> float
def smd_impinging(...) -> float
def swirl_solve(K) -> dict        # {'X','cd','theta_deg','film_t_ratio'}
def pintle_spray_angle(tmr) -> float
```

### B.1 `spec` girişi (JSON şeması gibi)

| Alan | Tip | Birim | Zorunlu | Varsayılan / açıklama |
|---|---|---|---|---|
| `motor_type` | `'hybrid'\|'liquid'` | — | evet | — |
| `injector_type` | `'showerhead'\|'impinging_doublet'\|'impinging_triplet'\|'like_impinging'\|'pintle'\|'coax_swirl'\|'swirl'` | — | hayır | hybrid→`showerhead`, liquid→`impinging_doublet` |
| `mdot_ox` | float > 0 | kg/s | evet | — |
| `mdot_fuel` | float > 0 | kg/s | liquid'de evet | hybrid'de verilmez/None → `fuel_circuit=None` |
| `rho_ox` | float | kg/m³ | evet (n2o'da tablo ezerse ops.) | `fluid_ox='n2o'` + `T_ox_K` verilirse doyma tablosundan |
| `rho_fuel` | float | kg/m³ | liquid'de evet | — |
| `Pc_bar` | float > 0 | bar | evet | oda basıncı |
| `dp_ratio_ox` / `dp_ratio_fuel` | float | — | hayır | 0.20 (bant 0.10-0.40; <0.15 uyarı) |
| `fluid_ox` | `'n2o'\|'lox'\|'generic'` | — | hayır | `'generic'`; `'n2o'` → NHNE yolu |
| `T_ox_K` | float | K | n2o'da evet | doyma özellikleri için |
| `p_feed_bar` | float | bar | hayır | verilmezse `Pc·(1+dp_ratio)`; n2o'da P₁=min(p_feed, P_sat) doyma kontrolü |
| `inlet_ox` / `inlet_fuel` | `'sharp'\|'radiused'` | — | hayır | `'sharp'` |
| `l_over_d` | float | — | hayır | 4.0 |
| `orifice_constraints` | dict | mm | hayır | `{'d_min_mm':0.3,'d_max_mm':3.0,'n_max':120}` |
| `sigma_ox`/`sigma_fuel` | float | N/m | hayır | 0.02 |
| `mu_ox`/`mu_fuel` | float | Pa·s | hayır | 2e-4 |
| `T_c_K`, `mw_gas` | float | K, kg/kmol | hayır | verilirse ρ_A hesabında; yoksa ρ_A=5 kg/m³ varsayılan + assumption notu |
| `pintle` | dict | — | pintle'da hayır | `{'d_pintle_mm': None (otomatik), 'bf_target':0.58,'tmr_target':1.0}` |
| `swirl` | dict | — | swirl'de hayır | `{'K': None (θ hedefinden), 'theta_target_deg':45}` |
| `target_velocity_ratio` | float | — | hayır | doublet MR hedefi 1.0 |

Geçersiz girişte `ValueError` (mesaj Türkçe) — endpoint bunu 400'e çevirir.

### B.2 Dönen dict (tam şema)

```python
{
  'status': 'success',
  'motor_type': str, 'injector_type': str,
  'ox_circuit': {                             # HER ZAMAN dolu
     'mdot_kg_s': float, 'delta_p_bar': float, 'dp_pc_ratio': float,
     'velocity_m_s': float, 'cd': float, 'cd_basis': str,      # ör. "keskin giriş, L/D=4 → 0.78 (SP-8089)"
     'n_orifices': int, 'orifice_d_mm': float, 'total_area_mm2': float,
     'flow_model': 'SPI'|'NHNE',
     'nhne': None | {'kappa': float, 'mdot_spi_kg_s': float,
                     'mdot_hem_kg_s': float, 'p_sat_bar': float,
                     'quality_out': float},
     'cavitation_number': float, 'hydraulic_flip_risk': bool,
     'manifold': {'d_mm': float, 'velocity_m_s': float,
                  'v_ratio': float, 'area_ratio': float},
  },
  'fuel_circuit': None | {aynı şema (flow_model her zaman 'SPI')},
  'pattern': {
     'description_tr': str,                   # "16 çift unlike doublet, 2θ=60°..."
     'n_elements': int,
     'impingement': None | {'half_angle_deg': float,
                            'free_jet_length_mm': float,
                            'element_spacing_mm': float},
  },
  'atomization': {
     'smd_ox_um': float, 'smd_fuel_um': float | None,
     'correlation': str,                      # 'Elkotb-1982' | 'Lefebvre-swirl' | 'impinging-We13'
     'spray_cone_half_angle_deg': float | None,
  },
  'momentum': None | {                        # impinging/pintle'da dolu
     'momentum_ratio': float | None,          # doublet MR
     'rupe_factor': float | None,
     'tmr': float | None,                     # pintle/triplet
     'target': float, 'ok': bool,
  },
  'pintle_geometry': None | {'d_pintle_mm': float, 'skip_distance_mm': float,
     'ls_over_dp': float, 'bf': float, 'annulus_gap_mm': float,
     'n_radial_holes': int, 'radial_hole_d_mm': float},
  'swirl_geometry': None | {'K': float, 'X_air_core': float, 'cd_swirl': float,
     'swirl_number': float, 'film_thickness_mm': float,
     'tangential_inlets': int, 'inlet_d_mm': float},
  'stability': {
     'dp_pc_ratio_ox': float, 'dp_pc_ratio_fuel': float | None,
     'chug_ok': bool, 'chug_rule': 'dP/Pc >= 0.15-0.20 (NASA SP-8089)',
     'feed_coupling_warning_tr': str | None,  # N₂O özel notu
     'acoustic_note_tr': str,
  },
  'warnings_tr': [str], 'assumptions_tr': [str],
  'references': [str],                        # kullanılan kaynak kısaltmaları
}
```

Hata yolu: `design_injector` doğrulama hatasında `ValueError` fırlatır;
fiziksel imkânsızlıkta (ör. delik kısıtlarıyla ṁ sağlanamıyor)
`{'status':'error','error': '<Türkçe mesaj>'}` döner.

### B.3 Çözüm sırası (implementasyon rehberi)

1. Girdi doğrulama + varsayılanlar; ΔP = dp_ratio·Pc.
2. Cd seçimi (`discharge_coefficient`) → gerekçe stringi.
3. Debi modeli: `fluid_ox='n2o'` → NHNE (P₁, P_sat(T_ox), P_c ile), değilse SPI.
4. Toplam alan → delik planı: `n` seçimi kısıtlar içinde d'yi 0.5-2.5 mm
   bandına oturtacak şekilde (yoksa en yakın sınır + uyarı).
5. Tipe özel geometri: impinging (açı/mesafe/MR/Rupe), pintle (BF→n·d,
   TMR→anülüs, skip), swirl (K veya θ hedefinden X, Cd_swirl → alan yeniden).
   Swirl'de etkin Cd, orifis Cd'sinin YERİNE geçer (alan büyür — fiziksel).
6. Manifold: v_man = 0.1·v_orifis hedefiyle çap; alan oranı raporu.
7. Atomizasyon: tipe göre korelasyon; ρ_A oda gazından.
8. Kararlılık kontrolleri + uyarı listesi.

---

## C. HTTP ENDPOINT SÖZLEŞMESİ

`POST /api/injector-design` (app.py):

- **İstek gövdesi:** B.1'deki `spec` alanları birebir (JSON). Ek kolaylık
  alanları: `from_results: true` gönderilirse sunucu istekteki
  `motor_results` bloğundan (`mdot_ox`, `mdot_fuel`, `Pc_bar`, `T_c_K`,
  `mw_gas`) doldurur — UI mevcut hesap sonucunu iletebilir.
- **Yanıt 200:** `{'status':'success', 'design': <B.2 şeması>}`
- **Yanıt 400:** `{'status':'error', 'error': '<Türkçe doğrulama mesajı>'}`
- **Yanıt 500:** `{'status':'error', 'error': '<beklenmeyen hata>'}`
- Endpoint saf hesaptır, dosya yazmaz; CORS mevcut app politikasını izler.

---

## D. UI GEREKSİNİMLERİ (liquid + advanced)

Ortak panel (tek kaynak `static/js/injector_panel.js` önerilir — sixdof_panel
deseniyle: `InjectorPanel.init({anchorId, motorType, resultsProvider})`):

**Girdi satırı:** enjektör tipi seçici (motor tipine göre filtreli) +
dp_ratio + (pintle/swirl için hedef parametre) + "Enjektörü Tasarla" butonu.
`resultsProvider()` mevcut hesap sonucundan ṁ/Pc/T_c'yi otomatik doldurur.

**Çıktı — rozetler (badge):**
- `ΔP/Pc %XX` (ok yeşil / <15% kırmızı `CHUG RİSKİ`)
- `MODEL: NHNE|SPI` (n2o'da NHNE değilse turuncu uyarı)
- `FLIP RİSKİ` (varsa kırmızı)
- `MR 0.49 → HEDEF 1.0` (bandın dışındaysa turuncu)
- `SMD ~85 µm (Elkotb)`

**Çıktı — tablo (devre başına):** delik sayısı, çap (mm), toplam alan (mm²),
ΔP (bar), hız (m/s), Cd (+gerekçe tooltip), manifold çapı/hız oranı.
**Tipe özel blok:** pintle (D_p, skip, BF, TMR, θ), swirl (K, X, Cd_s, θ, film),
impinging (açı, mesafe, eleman aralığı, Rupe).
**Uyarılar listesi:** `warnings_tr` maddeleri sarı kutuda; `assumptions_tr`
katlanabilir "Varsayımlar" bölümünde; `references` alt notta.

Yerleşim: liquid'de mevcut Injector Design panelinin altına; advanced'de
injector_config sekmesine. Tam genişlik: panel köküne `grid-column: 1 / -1`
(2026-07-13 6-DOF panel dersi).

---

## E. TEST PLANI (`tests/test_injector_design.py`)

Analitik/literatür bazlı assert'ler (uydurma referans yok):

1. `test_spi_closed_form`: Ö1 girdileriyle `ṁ = 0.1825 ± 0.001 kg/s`;
   `v = 29.1 ± 0.1 m/s`; ṁ=ρAv özdeşliği bin de birde.
2. `test_nhne_saturated_is_midpoint`: doymuş giriş (P₁=P_sat) → κ=1.0 (kesin)
   ve `ṁ_NHNE = (ṁ_SPI+ṁ_HEM)/2` (kesin); sıralama `HEM < NHNE < SPI`.
3. `test_nhne_subcooled_limit`: P₁ = P_sat+30 bar → `ṁ_NHNE/ṁ_SPI ≥ 0.97`.
4. `test_cd_table`: ('sharp',0.5)→0.61-0.65; ('sharp',4)→0.75-0.85;
   ('radiused',4)→0.88-0.95; gerekçe stringi boş değil.
5. `test_hydraulic_flip_flag`: sharp+L/D=3+K_c<1.5 → True;
   radiused aynı koşullar → False; sharp+L/D=8 → False.
6. `test_chug_guard`: dp_ratio=0.08 → `chug_ok=False` + 'chug' geçen uyarı;
   dp_ratio=0.20 → True.
7. `test_doublet_momentum_and_rupe`: Ö3 girdileriyle `MR=0.49±0.02`,
   `rupe_factor=0.70±0.03`, `momentum.ok=False`, uyarı üretilmiş.
8. `test_orifice_constraints`: `n_max=8` kısıtıyla n≤8; d bandı ihlalinde
   uyarı; alan toplamı ṁ'yi ±%1 sağlar.
9. `test_pintle_geometry`: TMR=1 → `θ=60°±5°` (arccos(1/2)); BF hedef
   0.58±0.05 bandında n·d çözülmüş; `ls_over_dp` 0.7-1.0.
10. `test_swirl_solution`: K=1.0 → X∈(0,1), `Cd_swirl<0.5`,
    `sinθ=(π/2)Cd/(K(1+√X))` özdeşliği; θ hedef 45° verilirse çözülen
    geometri θ'yı ±3° tutturur.
11. `test_smd_monotonic`: swirl SMD(ΔP=20 bar) < SMD(5 bar); Elkotb SMD
    20-1000 µm fiziksel bandında (Ö1 koşulları).
12. `test_manifold_rule`: `v_ratio ≤ 0.2` her tasarımda; `area_ratio ≥ 4`.
13. `test_hybrid_path`: motor_type='hybrid' → `fuel_circuit is None`;
    fluid_ox='n2o'+T=293 K → `flow_model='NHNE'`, `nhne.p_sat_bar≈50.4±0.5`.
14. `test_liquid_requires_fuel`: mdot_fuel eksik → ValueError (Türkçe mesaj).
15. `test_endpoint_contract` (app testi): POST /api/injector-design Ö1
    benzeri gövde → 200 + `design.ox_circuit.n_orifices` int; bozuk gövde → 400.

---

## F. KAYNAKÇA

1. NASA SP-8089, *Liquid Rocket Engine Injectors*, 1976.
2. Sutton & Biblarz, *Rocket Propulsion Elements*, 9. baskı, Böl. 8-9.
3. Huzel & Huang, *Modern Engineering for Design of Liquid-Propellant Rocket Engines*, Böl. 4.
4. Lefebvre & McDonell, *Atomization and Sprays*, 2. baskı, Böl. 2, 5, 6.
5. Dyer, Doran, Dunn, Zilliac, "Modeling Feed System Flow Physics for Self-Pressurizing Propellants", AIAA 2007-5702. (NHNE, ±%15 doğrulama)
6. Solomon, B., *Engineering Model to Calculate Mass Flow Rate of a Two-Phase Saturated Fluid Through an Injector Orifice*, Utah State, 2011.
7. Waxman, Zimmerman, Cantwell, Zilliac, Stanford N₂O enjektör deneyleri, 2013.
8. Nurick, W. H., "Orifice Cavitation and Its Effect on Spray Mixing", ASME J. Fluids Eng., 1976.
9. Rupe, J., "The Liquid-Phase Mixing of a Pair of Impinging Streams", JPL Progress Report 20-195, 1953.
10. Ingebo, R. D., NACA TN 3265: impinging jet damla boyutu (D₃₀) verisi.
11. Elkotb, M. M., "Fuel Atomization for Spray Modelling", Prog. Energy Combust. Sci., 1982.
12. Giffen & Muraszew, *The Atomisation of Liquid Fuels*, Chapman & Hall, 1953.
13. Casiano, Hulka, Yang, "Liquid-Propellant Rocket Engine Throttling: A Comprehensive Review", J. Propulsion & Power 26(5), 2010. (pintle)
14. Cheng ve ark., "On the prediction of spray angle of liquid-liquid pintle injectors", Acta Astronautica 138:145, 2017. (θ–TMR modeli)
15. Dressler & Bauer, "TRW Pintle Engine Heritage and Performance Characteristics", AIAA 2000-3871. (BF/skip mirası)
16. NASA NTRS 20190001326, "Mass Flow Rate and Isolation Characteristics of Injectors for Use with Self-Pressurizing Oxidizers in Hybrid Rockets".
