# Standart atıfları kayıt defteri

**Oluşturma:** 2 Ağustos 2026 · **Taban:** HEAD `a7ff1e7`
**Gerekçe:** Faz 4 denetimi (`docs/FAZ4_CODEX_TEYIT.md` §C) kodda 40 farklı
standart atfı olduğunu ve elle kontrol edilen **üç başlığın üçünün de yanlış**
olduğunu ölçtü. Bu defter, atıfların TAM adını tek bir yerde tutar;
`tools/iddia_lint.py` bilinen yanlış başlıkları makinece yakalar.

## Nasıl okunur

| Alan | Anlamı |
|---|---|
| **Durum** | `DOĞRULANDI` = resmi/birincil kaynaktan tam ad ve yıl teyit edildi. `DOĞRULANMADI` = bu turda kontrol edilmedi; başlığın doğru olduğu **varsayılmamalıdır**. |
| **Kaynak** | Doğrulamanın yapıldığı yer (NTRS, standards.nasa.gov, ISO, ANSI, NFPA, ASME). |
| **Kodda** | Atfın gerçekten hangi hesabı beslediği. |

**Kural:** Yeni bir standart atfı eklemeden önce buraya `DOĞRULANDI` satırı
gir. Doğrulayamıyorsan atfı koyma — kaynaksız bırakmak, yanlış kaynak
göstermekten iyidir.

---

## 1. Doğrulanmış atıflar

### NASA SP-8089 — 45 kullanım
* **Tam ad:** *Liquid Rocket Engine Injectors*
* **Yayın:** NASA Space Vehicle Design Criteria (Chemical Propulsion),
  Mart 1976. Yazarlar: G. S. Gill, W. H. Nurick (Rockwell International).
* **Durum:** DOĞRULANDI — NTRS ID `19760023196`, rapor numarası `NASA-SP-8089`.
* **Kodda:** enjektör basınç düşümü kararlılık eşikleri (ΔP/P_c),
  `hrma/analysis/transient_ballistics.py:27,41,414`; enjektör tasarımı ve
  `hrma/app.py:1059` aralık kontrolü.

### ISO 898-1 — 34 kullanım
* **Tam ad:** *Mechanical properties of fasteners made of carbon steel and
  alloy steel — Part 1: Bolts, screws and studs with specified property
  classes — Coarse thread and fine pitch thread*
* **Yayın:** ISO 898-1:2013 (5. baskı); 2025'te teyit edilerek yürürlükte.
* **Durum:** DOĞRULANDI — iso.org katalog kaydı (`std/60610`).
* **Kodda:** cıvata mukavemet sınıfı tablosu ve izin verilen çekme gerilmesi,
  `hrma/analysis/structural_analysis.py:11,1214,1232,1286` (gerilme alanı
  A_t üzerinden kapak cıvatası hesabı).
* **Not:** Table 3 madde numarası depo yorumundan gelir; madde metni ücretli
  standartta olduğu için ayrıca doğrulanmadı.

### NASA SP-125 — 27 kullanım
* **Tam ad:** *Design of Liquid Propellant Rocket Engines*
* **Yazarlar / yayın:** Dieter K. Huzel, David H. Huang (North American
  Rockwell, Rocketdyne). 1. baskı 1967, **2. baskı 1971**.
* **Durum:** DOĞRULANDI — NASA SP-125 künyesi, NTRS/ADS kaydı
  `1971NASSP.125.....H`.
* **Kodda:** ısı yutucu hazne sınırı `hrma/analysis/heat_transfer_analysis.py:1438`;
  çan lülesi eşdeğer koni yaklaşımı `hrma/analysis/nozzle_flow_1d.py:765`;
  enjektör orifis boyutlandırması `hrma/utils/injector_design.py:167`.
* **DİKKAT:** `hrma/app.py:5185` bu belgeye *"Liquid-Propellant Rocket Engine
  Performance"* diyor — **yanlış başlık**, açık borç (`iddia_lint --debt`).

### NASA SP-8124 — 20 kullanım
* **Tam ad:** *Liquid Rocket Engine Self-Cooled Combustion Chambers*
* **Yayın:** 1 Eylül 1977; NASA Space Vehicle Design Criteria. NTRS erişim
  numarası `78N21211`, NTRS ID `19780013268`.
* **Kapsam:** kendinden soğutmalı beş hazne tipi — ablatif, ışınımla
  soğutmalı, iç rejeneratif (Interegen), ısı yutucu, adyabatik cidar.
* **Durum:** DOĞRULANDI — NTRS kaydı.
* **Kodda:** `hrma/analysis/heat_transfer_analysis.py:16,1067` (gaz ışınımı ve
  cidar ısıl tasarımı); `hrma/engines/liquid_rocket_engine.py:2810,2875,3187`
  (Bartz recovery sıcaklığı bağlamında).
* **DİKKAT:** `hrma/app.py:5268` bu belgeye *"Thermal Design Criteria"* diyor
  — **yanlış başlık**, açık borç.

### NASA SP-8110 — 16 kullanım
* **Tam ad:** *Liquid Rocket Engine Turbines*
* **Yayın:** Ocak 1974; NASA Space Vehicle Design Criteria (Chemical
  Propulsion). NTRS ID `19740026132`.
* **Durum:** DOĞRULANDI — NTRS kaydı.
* **Kodda:** türbin verimi ve hız oranı bandı, soğutmasız kanat sıcaklık üst
  sınırı — `hrma/engines/cycle_power_balance.py:77,91,125,131`.

### NASA SP-8007 — 16 kullanım
* **Tam ad:** *Buckling of Thin-Walled Circular Cylinders*
* **Yayın:** NASA Space Vehicle Design Criteria (Structures), Ağustos 1968;
  1968/69 revizyonu. NTRS ID `19690013955`. (2019-2020'de yeni bir revizyon
  taslağı yayımlandı; depo klasik sürüme atıf yapıyor.)
* **Durum:** DOĞRULANDI — NTRS kaydı.
* **Kodda:** ince cidarlı silindirin eksenel ve dış basınç burkulması,
  `hrma/analysis/structural_analysis.py:152,337,347,352`.

### NASA-STD-5012 — 15 kullanım
* **Tam ad:** *Strength and Life Assessment Requirements for Liquid-Fueled
  Space Propulsion System Engines*
* **Yayın:** Rev. B, 16 Haziran 2016; standards.nasa.gov.
* **Kapsam:** motorun **yapısal kalifikasyonu** — mukavemet, yorulma ve
  sürünme ("life" = fatigue + creep) gereksinimleri, analiz ve testle
  nitelendirme.
* **Durum:** DOĞRULANDI — standards.nasa.gov / NASA-STD-5012B PDF künyesi.
* **Kodda kullanımı:** **YOK.** Bu belgeye dayanan hiçbir hesap yok. Bütün
  atıflar yanlıştı: hem başlık ("Pressure Vessels & Pressurized Systems")
  hem konu (lülede izantropik Mach-alan bağıntısı ve besleme hattı basınç
  düşümü) uyduruktu. Bir mukavemet/ömür standardı gaz dinamiği bağıntısının
  kaynağı olamaz.
* **Düzeltildi (2026-08-02, C2):** `hrma/templates/formulas.html:14.2/14.5`,
  `hrma/static/js/i18n_formulas.js` (EN+TR), `hrma/static/js/panels/performance_panel.js:7`,
  `hrma/export/pdf_generator.py`. **Açık borç:** `hrma/app.py:5191,5229`.

### AIAA S-080A — 15 kullanım (`AIAA S-080` yazımıyla) + 3 (`S-080A`)
* **Tam ad:** *Space Systems — Metallic Pressure Vessels, Pressurized
  Structures, and Pressure Components*
* **Yayın:** ANSI/AIAA S-080A-2018 (S-080-1998'in revizyonu); 2024'te teyit
  edildi.
* **Durum:** DOĞRULANDI — ANSI webstore / AIAA kaydı (`10.2514/4.105418.001`).
* **Kodda:** metalik basınçlı kap izin verilen gerilmesi ve proof faktörü,
  `hrma/analysis/pressure_vessel.py:25,44`; benzeşim yoluyla
  `hrma/analysis/water_hammer.py:207`.

### NFPA 1125 — 14 kullanım
* **Tam ad:** *Code for the Manufacture of Model Rocket and High-Power
  Rocket Motors*
* **Yayın:** NFPA; yürürlükteki baskılar 2017 / 2022 / 2026.
* **Durum:** Başlık DOĞRULANDI (nfpa.org ürün kaydı). **Baskı yılı ve
  %5 eşiğinin madde numarası DOĞRULANMADI** — kod hangi baskıya baktığını
  yazmıyor ve standart ücretli.
* **Kodda:** yanma süresi eşiği (tepe itkinin %5'i) —
  `hrma/importers/motor_file.py:39`, `hrma/app.py:5990`,
  `hrma/static/js/i18n_common.js:1248,1251`.

### ASME BPVC Section VIII, Division 1 — 11 kullanım (`ASME BPVC VIII-1`)
* **Tam ad:** *ASME Boiler and Pressure Vessel Code, Section VIII: Rules for
  Construction of Pressure Vessels, Division 1*
* **Yayın:** 2023 baskısı 1 Temmuz 2023'te yürürlüğe girdi.
* **Durum:** Başlık DOĞRULANDI (asme.org / ANSI webstore). **Madde
  numaraları (UG-25 korozyon payı, UG-27 cidar kalınlığı, UG-98 MAWP)
  DOĞRULANMADI** — ücretli standart, madde metni görülmedi; numaralar
  deponun kendi yorumlarından alındı.
* **Kodda:** `hrma/analysis/structural_analysis.py:30,37,753`;
  `hrma/analysis/safety_analysis.py:386` (`applicable_codes` listesi).

### NACA Report 1135 — 7 kullanım
* **Tam ad:** *Equations, Tables, and Charts for Compressible Flow*
* **Yazar / yayın:** Ames Research Staff, NACA Report 1135, 1953
  (NACA TN 1428'in genişletilmiş revizyonu).
* **Durum:** DOĞRULANDI — NASA barındırdığı tam metin PDF.
* **Kodda:** izantropik alan-Mach bağıntısı ve normal şok bağıntıları —
  `hrma/analysis/nozzle_flow_1d.py:12-26`; formül referans sayfası §14.2.
* **Not:** NASA-STD-5012'nin yerine geçen **doğru** kaynak budur.

### UFC 3-340-02 — 3 kullanım
* **Tam ad:** *Structures to Resist the Effects of Accidental Explosions*
* **Durum:** Başlık DOĞRULANMADI (bu turda kontrol edilmedi); kod
  Kingery-Bulmash / Kinney-Graham patlama ölçeklemesiyle birlikte anıyor.
* **Kodda:** tahliye mesafesi hesabı, `hrma/analysis/safety_analysis.py`
  (bkz. `tests/test_safety_honesty.py::test_sourced_blast_model_is_left_alone`).

---

## 2. Standart olmayan ama atıf verilen birincil kaynaklar

Bunlar standart değil, literatürdür; kayda geçirilmelerinin nedeni C2/C3'te
yanlış standartların yerine **bunların** konmuş olmasıdır.

| Kaynak | Tam künye | Durum | Kodda |
|---|---|---|---|
| Bartz 1957 | D. R. Bartz, "A Simple Equation for Rapid Estimation of Rocket Nozzle Convective Heat Transfer Coefficients", *Jet Propulsion* 27 (1957) | DOĞRULANMADI (künye depo yorumlarından) | gaz tarafı ısı taşınım katsayısı, `heat_transfer_analysis.py` |
| Anderson | J. D. Anderson, *Modern Compressible Flow*, 3. baskı | DOĞRULANMADI | alan-Mach ve normal şok bağıntıları, `nozzle_flow_1d.py:12-26` |
| Sutton & Biblarz | G. P. Sutton, O. Biblarz, *Rocket Propulsion Elements*, 9. baskı | DOĞRULANMADI | orifis akışı (Böl. 8), lüle kayıpları (Böl. 3), çevrimler (Böl. 6/10) |
| Dittus & Boelter 1930 | Univ. of California Publications in Engineering 2:443 (1930) | DOĞRULANMADI | soğutucu tarafı Nu korelasyonu |
| Summerfield 1954 | Summerfield, Foster, Swan, "Flow Separation in Overexpanded Supersonic Exhaust Nozzles", *Jet Propulsion* 24 (1954) | DOĞRULANMADI | akış ayrılması ölçütü, `nozzle_flow_1d.py:31-38` |
| Giffen & Muraszew 1953 | basınç-swirl atomizasyon çözümü | DOĞRULANMADI | swirl enjektör, `injector_design.py:500,511` |

---

## 3. DOĞRULANMADI — kalan atıflar

Aşağıdaki numaralar kodda geçiyor ama **bu turda başlıkları kontrol
edilmedi**. Doğru oldukları varsayılmamalıdır: kontrol edilen ilk üç
başlığın üçü de yanlış çıktı.

| Atıf | Kullanım | Atıf | Kullanım |
|---|---:|---|---:|
| ISO 3506-1 | 12 | NASA SP-8091 | 10 |
| ISO 2768-1 | 10 | NASA SP-8064 | 9 |
| NASA-STD-5020A | 8 | NASA SP-8051 | 7 |
| NASA SP-8031 | 7 | ASME Section V | 7 |
| NASA SP-8120 | 5 | NASA SP-8073 | 5 |
| ISO 2533 | 5 | NASA SP-8004 | 4 |
| NASA SP-194 | 4 | NASA SP-106 | 4 |
| ASTM A36 | 4 | NASA SP-8107 | 3 |
| AWS D17.1 | 3 | AWS D1.1 | 3 |
| API 520 | 3 | NFPA 495 | 2 |
| NASA SP-8009 | 2 | MIL-STD-210 | 2 |
| ISO 80000-3 | 2 | ISO 1302 | 2 |
| ASTM B265 | 2 | ASME BPVC VIII-2 | 2 |
| API 521 | 2 | NASA SP-8093 | 1 |
| NASA SP-8087 | 1 | NASA SP-8075 | 1 |
| ISO 13732-1 | 1 | ISO 10303-21 | 1 |
| EN 13445 | 1 | ASME III NB-3222 | 1 |
| AS 1210 | 1 | | |

---

## 4. Makine denetimi

```bash
python3 tools/iddia_lint.py          # kayıtsız iddia/başlık isabeti varsa çıkış 1
python3 tools/iddia_lint.py --debt   # kapatılmayı bekleyen AÇIK BORÇ satırları
```

Bekçi testi: `tests/test_faz4_iddia_dili.py`. Bilinen yanlış başlıklar
`tools/iddia_lint.py` içindeki `WRONG_STANDARD_TITLES` kural kümesindedir;
yeni bir yanlış başlık bulunduğunda hem oraya hem bu deftere işlenir.
