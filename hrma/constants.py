"""
HRMA Fiziksel Sabitler Modülü
=============================
Tüm motor modüllerinin (hybrid, liquid, solid, nozzle, combustion, analysis)
ortak kullandığı fiziksel sabitler tek bir merkezde toplanmıştır.

Magic-number tutarsızlıkları (örn. 9.81 vs 9.80665, 8314.0 vs 8314.46) bu
modül üzerinden import edilerek önlenir.

Kaynaklar:
- CODATA 2018 (R_universal)
- ISO 80000-3 / BIPM (g_0 standart yerçekimi)
- ICAO Standart Atmosfer 1993 (atmosfer parametreleri)
"""

from typing import Optional

# -----------------------------------------------------------------------------
# Yerçekimi sabiti
# -----------------------------------------------------------------------------
# Standart yerçekimi ivmesi (BIPM tanımı). I_sp = F / (mdot * g_0) tanımında
# kullanılan referans değer. 9.81 yerine bu kullanılmalıdır.
G_0 = 9.80665  # m/s^2 (kesin standart değer)

# Geriye uyum: bazı modüllerde lower-case kullanılıyordu
g_0 = G_0
g0 = G_0

# -----------------------------------------------------------------------------
# Gaz sabitleri
# -----------------------------------------------------------------------------
# Universal gaz sabiti (CODATA 2018)
# Birim: J/(kmol*K) -- molekül ağırlığı kg/kmol cinsinden alınırsa R_u/MW = J/(kg*K)
R_UNIVERSAL = 8314.462618  # J/(kmol*K)
R_universal = R_UNIVERSAL  # geriye uyum

# Aynı sabitin MOL tabanı. NASA 7-katsayılı polinomları (Cp/R = a1 + a2*T + ...)
# mol başına çalışır ve katsayı tabloları J/(mol*K) bekler; chemical_database
# içindeki Cp/H/S hesapları bu adı kullanır.
#
# ÖH D24 / P10B3-10 — SAYI DEĞİŞTİ, BEYANLI: chemical_database üç yerde
# ``R = 8.314`` yazıyordu (kesilmiş değer, CODATA değil). 8,314 ->
# 8,314462618; bağıl fark +5,5644e-5. Sabit R_UNIVERSAL'den TÜRETİLİR
# (bölme burada bir kez yapılır) ki kmol ve mol tabanlı iki okuma asla
# ayrışamasın.
R_MOLAR = R_UNIVERSAL / 1000.0  # J/(mol*K) = 8.314462618

# ICAO atmosfer hesaplarında kullanılan gaz sabiti (J/(mol*K), CODATA)
# DİKKAT: bu R_MOLAR DEĞİLDİR. ICAO 1993 standardı R* = 8,31432 J/(mol*K)
# değerini TANIM olarak sabitler (eski CODATA); atmosfer tablolarının
# yeniden üretilebilirliği bu değere bağlıdır ve güncel CODATA ile
# değiştirilmesi tabloyu bozar. Termokimya için R_MOLAR kullanılır.
R_STAR_ICAO = 8.31432  # J/(mol*K) -- ICAO 1993 tanımı

# -----------------------------------------------------------------------------
# Stefan-Boltzmann sabiti (CODATA 2018, kesin türetilmiş değer)
# -----------------------------------------------------------------------------
# v2.6.27 merkezîleştirmesi: bu sabit 6 ayrı dosyada ayrı ayrı tanımlıydı
# (thermal_protection, heat_transfer_analysis, solid_rocket_engine
# SOLID_THERMAL, safety_analysis, structural_analysis, fea/thermal_axisym).
# Değerler aynıydı ama tek-tanım-noktası kuralı çiğneniyordu; hepsi artık
# buradan okur. Işınım terimleri: q = eps * sigma * T^4.
STEFAN_BOLTZMANN = 5.670374419e-8  # W/(m^2*K^4)

# -----------------------------------------------------------------------------
# ICAO Standart Atmosfer Sabitleri
# -----------------------------------------------------------------------------
M_AIR = 0.0289644  # kg/mol -- kuru havanın ortalama molar kütlesi (ICAO)
T_TROPOPAUSE = 216.65  # K -- 11 km'de sabit sıcaklık
P_TROPOPAUSE = 22632.1  # Pa -- 11 km'de basınç
H_TROPOPAUSE = 11000.0  # m

# US Standard Atmosphere 1976 / ICAO katman tablosu (0-84.852 km geopotansiyel)
# Her kayıt: (h_taban [m], T_taban [K], lapse [K/m], P_taban [Pa])
# Kaynak: U.S. Standard Atmosphere 1976 (NOAA/NASA/USAF), Tablo 4
ISA_LAYERS = [
    (0.0,     288.15, -0.0065, 101325.0),
    (11000.0, 216.65,  0.0,    22632.1),
    (20000.0, 216.65,  0.001,  5474.89),
    (32000.0, 228.65,  0.0028, 868.019),
    (47000.0, 270.65,  0.0,    110.906),
    (51000.0, 270.65, -0.0028, 66.9389),
    (71000.0, 214.65, -0.002,  3.95642),
]

#: Deniz seviyesi standart basıncı [Pa]. YENİ BİR SAYI DEĞİLDİR: ISA
#: tablosunun kendi taban satırından okunur, ikinci bir literal yazılmaz.
#:
#: ÖH D26 / defter P15B2-06 (kalan). R ve g_0 ayakları fix aşamasında
#: kapandı; ÖLÇÜLDÜ (taban 7751531,
#: ``raw/OH/D26/ihracat/a1/once.json`` -> ``P15B2-06``): ``hrma/data``
#: altında R / g_0 / Stefan-Boltzmann literali 0 kalmıştı ama aynı sınıftan
#: BEŞ ``101325`` literali duruyordu (``chemical_database`` 2,
#: ``open_source_propellant_api`` 3) ve merkezde adı olan bir sabit yoktu.
P_SEA_LEVEL_PA = ISA_LAYERS[0][3]  # Pa

# ISA tablo üst sınırı (geopotansiyel). Üzerinde son katmandan izotermal
# uzantı kullanılır (T tablo tepesindeki değerde sabitlenir; basınç üstel
# sönümle devam eder — sayısal kararlılık, negatif T/P engellenir).
ISA_TABLE_TOP_M = 84852.0  # m
# ISA tablo ALT sınırı (geopotansiyel). US Standard Atmosphere 1976 tabloları
# −5 km geopotansiyel yükseklikten başlar (NOAA/NASA/USAF, 1976, Tablo I);
# deniz seviyesi altındaki gerçek sahalar (Ölüdeniz −430 m, Turfan −154 m,
# Danakil −125 m) bu aralığın İÇİNDEDİR ve troposfer katmanının
# (ISA_LAYERS[0], lapse −0,0065 K/m) aşağı doğru uzantısıyla çözülür.
# ÖH D24 / OH-D23-07: ``TrajectoryAnalyzer._atm_full`` 0 m altını 0'a
# KIRPIYORDU (ölçüldü, a2/once.json K1: _atm_full(−400) = _atm_full(−500) =
# _atm_full(0) = 101325,0 Pa iken isa_pressure(−400) = 106223,74 Pa —
# aynı irtifada %4,61 ayrışan İKİ ISA okuması). Kırpma kalktı; bu sabit
# hem atmosferin hem de atış koşulu bandının ORTAK tabanıdır.
ISA_TABLE_BOTTOM_M = -5000.0  # m
# Altı katman sınırının tamamının sürekli olduğu ve tepe sıcaklığının
# 186,946 K olduğu Lean ile ispatlandı: HRMA.isaLayers_all_continuous,
# HRMA.isaTopTemperature (bkz. docs/BICIMSEL_ISPATLAR.md).


def _isa_layer(altitude_m: float):
    """ISA_LAYERS içinden verilen geopotansiyel irtifanın katmanını seçer."""
    layer = ISA_LAYERS[0]
    for candidate in ISA_LAYERS:
        if altitude_m >= candidate[0]:
            layer = candidate
        else:
            break
    return layer


def isa_temperature(altitude_m: float) -> float:
    """US Standard Atmosphere 1976 sıcaklığı [K], geopotansiyel irtifa [m].

    Satır-içi ISA kopyalarını tekilleştirir (combustion_analysis /
    liquid_rocket_engine eski yerel formülleri bu yardımcıya bağlandı).
    Negatif irtifada troposfer formülü ekstrapole edilir; tablo üstünde
    (>84.852 km) sıcaklık tablo tepesindeki değerde sabitlenir.
    """
    h = float(altitude_m)
    if h > ISA_TABLE_TOP_M:
        h_base, T_base, lapse, _ = ISA_LAYERS[-1]
        return T_base + lapse * (ISA_TABLE_TOP_M - h_base)
    h_base, T_base, lapse, _ = _isa_layer(h)
    return T_base + lapse * (h - h_base)


def isa_pressure(altitude_m: float) -> float:
    """US Standard Atmosphere 1976 basıncı [Pa], geopotansiyel irtifa [m].

    Katman formülleri (US Std Atm 1976, Eq. 33a/33b):
      lapse != 0:  P = P_b * (T/T_b)^(-g0*M/(R*·L))
      lapse == 0:  P = P_b * exp(-g0*M*(h-h_b)/(R*·T_b))
    Tablo üstünde (>84.852 km) tablo tepesi sıcaklığıyla izotermal uzantı.
    """
    import numpy as np
    h = float(altitude_m)
    if h > ISA_TABLE_TOP_M:
        h_base, T_base, lapse, P_base = ISA_LAYERS[-1]
        T_top = T_base + lapse * (ISA_TABLE_TOP_M - h_base)
        P_top = P_base * (T_top / T_base) ** (
            -G_0 * M_AIR / (R_STAR_ICAO * lapse))
        return float(
            P_top * np.exp(-G_0 * M_AIR * (h - ISA_TABLE_TOP_M)
                           / (R_STAR_ICAO * T_top)))
    h_base, T_base, lapse, P_base = _isa_layer(h)
    if lapse == 0.0:
        return float(
            P_base * np.exp(-G_0 * M_AIR * (h - h_base)
                            / (R_STAR_ICAO * T_base)))
    T = T_base + lapse * (h - h_base)
    return float(P_base * (T / T_base) ** (-G_0 * M_AIR / (R_STAR_ICAO * lapse)))

# -----------------------------------------------------------------------------
# Birim Çevirim Sabitleri
# -----------------------------------------------------------------------------
PA_PER_BAR = 1e5  # 1 bar = 100000 Pa
BAR_PER_PA = 1e-5

# ÖH D29 / app-api-dogrulama a1 · defter P15B2-10 — PSI ÇEVRİMİNİN TEK
# TANIM NOKTASI.
#
# ÖLÇÜLDÜ (taban 4c27fa51, ``once.json`` -> ``P15B2-10``): aynı çevrim
# depoda DÖRT AYRI ONDALIK KOPYA olarak yazılıydı ve üçü türetilmiş
# değerden sapıyordu:
#
#   hrma/analysis/two_phase_loss.py:145      14.503773773   (sapma 1,4e-12)
#   hrma/engines/cycle_power_balance.py:337  14.503773773   (sapma 1,4e-12)
#   hrma/engines/cea_bridge.py:50            14.5037738     (sapma 1,9e-09)
#   hrma/data/external_data_fetcher.py:645   14.5038        (sapma 1,8e-06)
#
# Üstelik ``cea_bridge.py`` kopyasının başlığı "Birim sabitleri — TEK
# doğruluk kaynağı" diyordu. Sayı İCAT EDİLMEDİ: psi KESİN TANIMLARDAN
# türetilir (1 lb = 0,45359237 kg tam; 1 in = 0,0254 m tam; 1 lbf = 1 lb·g_0),
# yani 1 psi = 6894,757293168 Pa. Bu, deponun kendi birim tablosundaki
# (``hrma/validation/record_adapters.UNIT_TO_SI['psi']``) katsayının ve
# ``hrma/analysis/valve_feedline.PSI_PA``in AYNISIdır; ikisi de artık
# buradan okur, ikinci bir literal yazılmaz.
IN_M = 0.0254            # 1 inch = 0,0254 m (uluslararası tanım, TAM)
LB_KG = 0.45359237       # 1 lb (avoirdupois) = 0,45359237 kg (TAM)
PA_PER_PSI = LB_KG * G_0 / (IN_M ** 2)   # 1 psi = lbf/in^2 -> ~6894,757293168 Pa
PSIA_PER_BAR = PA_PER_BAR / PA_PER_PSI   # 1 bar -> ~14,503773773 psia

# -----------------------------------------------------------------------------
# Motor türleri — alan sözlüğü (v2.6.27 merkezîleştirmesi)
# -----------------------------------------------------------------------------
# Bu bir FİZİKSEL sabit değil, alan sözlüğüdür; yine de "bir kavram, bir tanım
# noktası" kuralı (CLAUDE.md kural 11) aynen geçerlidir. Üç ayrı dosya bu üçlüyü
# kendi başına tanımlıyordu ve biçimleri bile ayrışmıştı:
#   hrma/utils/projects.py            frozenset(['hybrid','solid','liquid'])
#   hrma/validation/experiment_db.py  ("hybrid","solid","liquid")
#   tests/test_panel_units_v2626.py   ('hybrid','solid','liquid')
# Değerler aynıydı — yani kusur değil, birinin sessizce ayrışmasına açık kapıydı
# (yeni bir motor türü eklenirse üç yerin ikisi güncellenir, biri unutulur).
#
# TEK KAYNAK SIRALI DEMETTİR, çünkü sıra semantik taşıyor:
#   * experiment_db.load_records kayıt klasörlerini BU SIRAYLA geziyor
#     (experiment_db.py:458 ``for subdir_name in MOTOR_TYPES``), yani üretilen
#     kayıt listesinin sırası buradan geliyor;
#   * geçersiz motor_type hata metinleri ``list(MOTOR_TYPES)`` basıyor;
#   * panel testi bununla parametrize oluyor (test kimlikleri bu sıradan).
# Üyelik soran yerler için küme biçimi aşağıda TÜRETİLİR (elle ikinci bir
# literal yazılmaz — ikisinin ayrışması yapısal olarak imkânsız).
MOTOR_TYPES = ("hybrid", "solid", "liquid")
MOTOR_TYPE_SET = frozenset(MOTOR_TYPES)

# -----------------------------------------------------------------------------
# Makul c* Bantları — oksitleyici-farkında fiziksel doğrulama (v2.5.0 G4)
# -----------------------------------------------------------------------------
# Teorik denge c* (m/s) için makullük bandı; hibrit HC yakıtları (HTPB,
# parafin, PE, PMMA, ABS, PLA), Pc 5-50 bar. Eski tek bant (1000-1900)
# N2O-merkezliydi: LOX/GOX çiftlerinde meşru ~1830 m/s değerler tavana
# dayanıyor, N2O'da ise gerçek anomaliler (1700+) kaçıyordu.
# Dayanak (NASA CEA maksimumları + ~%8 pay): N2O-HC maks ~1621 -> 1750;
# GOX/LOX-HC maks ~1812 -> 1950/1980; H2O2(%98)-HC maks ~1673 -> 1780.
# Alt sınırlar aşırı yakıt-zengin lab koşulları (örn. N2O O/F~1.2-1.5,
# CEA ~1200-1280) eksi pay. 'air' bandı hava-solunumlu akademik testler
# için kaba tahmindir (belirsiz). Bant eta_c_star uygulanmadan önce,
# TEORİK c* üzerinde denetlenir.
C_STAR_PLAUSIBLE_BAND_MPS = {
    'n2o': (950.0, 1750.0),
    'lox': (1100.0, 1950.0),
    'gox': (1100.0, 1980.0),
    'o2': (1100.0, 1980.0),
    'oxygen': (1100.0, 1980.0),
    'h2o2': (900.0, 1780.0),
    'air': (600.0, 1400.0),
}
C_STAR_BAND_DEFAULT_MPS = (900.0, 2000.0)  # bilinmeyen oksitleyici: geniş bant

# -----------------------------------------------------------------------------
# Nozzle Diverjans Düzeltme Faktörleri (lambda)
# -----------------------------------------------------------------------------
# lambda = (1 + cos(alpha)) / 2 formülünden türetilmiş değerler
# Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı
LAMBDA_BELL = 0.985            # Rao-optimize bell nozzle
LAMBDA_PARABOLIC = 0.975       # Parabolik kontur
LAMBDA_CONICAL_15DEG = 0.983   # 15 derece yarı açılı konik (1+cos(15°))/2 = 0.98296
LAMBDA_CONICAL_20DEG = 0.970   # 20 derece yarı açılı konik (1+cos(20°))/2 = 0.96985

# -----------------------------------------------------------------------------
# Lüle sürtünme / sınır tabaka itki kaybı kesri
# -----------------------------------------------------------------------------
# Yaklaşık sürtünme + sınır tabaka itki kaybı; tipik bant %0.5-2
# (Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı, Böl. 3.5).
# TEK TANIM YERİ (CLAUDE.md kural 11): hem nozzle_flow_1d.NozzleFlow1D
# varsayılanı hem sıvı motor teslim-Isp zinciri bu değeri kullanır — daha
# önce ikisi ayrı ayrı 0.015 yazıyordu.
#
# 16 AĞU 2026'DAN BERİ YALNIZ YEDEK (yarı-1B lüle zincirinde).
# Berke kararı ("doğrusu neyse o olsun"): NozzleFlow1D'nin YAYIMLADIĞI
# sürtünme kaybı artık ÖLÇÜLEN momentum-integral sınır tabakası değeridir
# (hrma/flow/boundary_layer.py). Bu sabit orada yalnızca ölçüm
# yayımlanamadığında devreye girer (lüle içi normal şok, boğulmamış akış,
# sınır tabakası kapalı/başarısız) ve kullanıldığında
# losses.friction_loss_fraction_source == 'legacy_constant' diye BEYAN
# EDİLİR. Göç manifestosu: tests/flow/test_surtunme_gocu.py.
# DEĞER DEĞİŞMEDİ (0.015) ve DEĞİŞTİRİLMEYECEK: sıvı motor teslim-Isp
# zinciri (liquid_rocket_engine.py eta_f) hâlâ bu sabiti kullanıyor;
# oradaki göç ayrı bir karardır (o zincirin kendi sınır tabakası çözümü
# yok). ÖLÇÜLDÜ (9 vakalık manifest): gerçek sürtünme kaybı 0,0095-0,0173
# bandında ve boğaz çapına kuvvetle bağlı — bu sabit büyük lülelerde
# KÖTÜMSER, ~12 mm'nin altındaki boğazlarda İYİMSERDİR.
NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT = 0.015


def lambda_conical(half_angle_deg: float) -> float:
    """Konik nozzle diverjans düzeltme faktörünü hesaplar.

    lambda = (1 + cos(alpha)) / 2

    Parametreler:
        half_angle_deg: Konik yarı açısı (derece)

    Döndürür:
        lambda (boyutsuz, 0 ile 1 arasında)
    """
    import numpy as np
    return 0.5 * (1.0 + np.cos(np.radians(half_angle_deg)))


def exit_pressure_ratio(epsilon: float, gamma: float) -> float:
    """Verilen alan oranı ve gamma icin Pe/Pc (SÜPERSONİK dal).

    İzentropik alan-oranı bağıntısı tersine çözülür::

        eps = (2/(g+1))^(1/(g-1)) * (Pc/Pe)^(1/g)
              / sqrt( ((g+1)/(g-1)) * (1 - (Pe/Pc)^((g-1)/g)) )

    Bağıntı boğazda (Pe/Pc = kritik oran) en küçük değerini alır ve iki
    dallıdır; burada YALNIZ süpersonik dal (Pe/Pc < kritik) köşelenir.

    Hata durumları FAIL-CLOSED: eps <= 1 ya da gamma <= 1 için ``ValueError``.
    """
    import numpy as np
    from scipy.optimize import brentq

    eps = float(epsilon)
    g = float(gamma)
    if not (eps > 1.0):
        raise ValueError('alan orani epsilon > 1 olmali (verilen: %r)' % epsilon)
    if not (g > 1.0):
        raise ValueError('gamma > 1 olmali (verilen: %r)' % gamma)

    kritik = (2.0 / (g + 1.0)) ** (g / (g - 1.0))

    def _fark(x: float) -> float:
        pay = (2.0 / (g + 1.0)) ** (1.0 / (g - 1.0)) * (1.0 / x) ** (1.0 / g)
        payda = np.sqrt(((g + 1.0) / (g - 1.0)) * (1.0 - x ** ((g - 1.0) / g)))
        return pay / payda - eps

    return float(brentq(_fark, 1e-14, kritik * (1.0 - 1e-12),
                        xtol=1e-16, rtol=8.9e-16))


def vacuum_isp_ratio(epsilon: float, gamma: float = 1.22,
                     chamber_pressure_bar: Optional[float] = None,
                     ambient_pressure_bar: Optional[float] = None) -> float:
    """Vakum / ortam Isp oranini IZENTROPIK Cf'ten hesaplar.

    ÖH D22 · P10B3-16 — BU FONKSİYON YENİDEN YAZILDI.

    Eski hâli ``0.953 + 0.0405*ln(eps) + 0.005*(gamma-1.2)`` ampirik
    log-fitiydi ve docstring'i "Sutton Tablo 3-2 ile kalibre edilmiştir"
    diyordu. Ölçüldü (``docs/scofield/raw/P10/B3-rapor.md#P10B3-16``):

    * Oran ODA BASINCINA bağlıdır, fonksiyon Pc'yi HİÇ ALMIYORDU. Aynı
      eps = 10'da gerçek oran Pc = 50 bar'da 1,1326, Pc = 300 bar'da
      1,0199 — fonksiyon ikisine de 1,0464 diyordu (−%7,6 / +%2,6).
    * ``gamma`` SÜS PARAMETREYDİ: 1,15 → 1,30 aralığında sonucu
      %0,069 değiştiriyordu.

    Bugünkü hesap tam izentropik itki katsayısı oranıdır::

        Cf_mom = sqrt( (2g^2/(g-1)) * (2/(g+1))^((g+1)/(g-1))
                       * (1 - (Pe/Pc)^((g-1)/g)) )
        Cf_vac = Cf_mom + eps*(Pe/Pc)
        Cf_amb = Cf_mom + eps*(Pe/Pc - Pa/Pc)
        oran   = Cf_vac / Cf_amb

    Raporun ölçtüğü beş referans noktasının BEŞİNİ de %0,002 içinde
    yeniden üretir (``docs/scofield/raw/OH/D22/altyapi/a1/sonra.json``)
    ve gamma duyarlılığı %0,069'dan %0,7'ye çıkar — parametre artık süs
    değil.

    FAIL-CLOSED iki kapı:

    * ``chamber_pressure_bar`` ZORUNLUDUR. Verilmezse ``ValueError``;
      sessiz bir varsayılan oda basıncı UYDURULMAZ.
    * Pe/Pa < 0,4 (Summerfield ayrılma ölçütü) ise akış lüle içinde
      ayrılmıştır ve tam dolu lüle Cf'i ortam itkisini temsil etmez —
      ``ValueError``, sayı YAYIMLANMAZ.

    Parametreler:
        epsilon: alan oranı Ae/At (> 1)
        gamma: özgül ısı oranı (> 1)
        chamber_pressure_bar: oda basıncı [bar] (zorunlu, > 0)
        ambient_pressure_bar: ortam basıncı [bar]; verilmezse ISA deniz
            seviyesi (``ISA_LAYERS[0]``, 1,01325 bar)

    Döndürür:
        Isp_vakum / Isp_ortam oranı (boyutsuz, > 1)
    """
    import numpy as np

    # Akışın lüle içinde AYRILDIĞI kabul edilen basınç oranı sınırı
    # (Summerfield ölçütü, Pe/Pa). Bu sınırın altında tam dolu lüle Cf'i
    # ortam itkisini TEMSİL ETMEZ. Ağaçta TEK yerde kullanılır (burada) —
    # merkezî sabit yapılmadı: tüketicisi olmayan merkezî sabit "tek
    # kaynak" yanılsaması üretir (tests/test_d20_altyapi_a1.py mandalı).
    ayrilma_pe_over_pa_siniri = 0.4
    # ISA deniz seviyesi ortam basıncı [bar] — TEK KAYNAK ``ISA_LAYERS[0]``.
    deniz_seviyesi_bar = ISA_LAYERS[0][3] * BAR_PER_PA

    if chamber_pressure_bar is None:
        raise ValueError(
            'vacuum_isp_ratio oda basincini ZORUNLU ister: oran Pc ile '
            '1,02-1,13 arasinda degisir (P10B3-16 olcumu). '
            'chamber_pressure_bar [bar] verin.')
    pc = float(chamber_pressure_bar)
    if not (pc > 0.0):
        raise ValueError('chamber_pressure_bar > 0 olmali (verilen: %r)'
                         % chamber_pressure_bar)
    pa = (deniz_seviyesi_bar if ambient_pressure_bar is None
          else float(ambient_pressure_bar))
    if not (pa > 0.0):
        raise ValueError('ambient_pressure_bar > 0 olmali (verilen: %r)'
                         % ambient_pressure_bar)

    g = float(gamma)
    eps = float(epsilon)
    x = exit_pressure_ratio(eps, g)          # Pe/Pc

    pe_over_pa = x * pc / pa
    if pe_over_pa < ayrilma_pe_over_pa_siniri:
        raise ValueError(
            'akis lulede AYRILMIS (Pe/Pa = %.3f < %.2f): tam dolu lule '
            'itki katsayisi ortam itkisini temsil etmez, oran '
            'yayimlanmaz. eps=%g, Pc=%g bar, Pa=%g bar.'
            % (pe_over_pa, ayrilma_pe_over_pa_siniri, eps, pc, pa))

    cf_mom = np.sqrt((2.0 * g * g / (g - 1.0))
                     * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0))
                     * (1.0 - x ** ((g - 1.0) / g)))
    cf_vac = cf_mom + eps * x
    cf_amb = cf_mom + eps * (x - pa / pc)
    if not (cf_amb > 0.0):
        raise ValueError(
            'ortam itki katsayisi pozitif degil (Cf_amb = %.4f): bu '
            'calisma noktasi fiziksel degil, oran yayimlanmaz.' % cf_amb)
    return float(cf_vac / cf_amb)


# -----------------------------------------------------------------------------
# Karakteristik uzunluk L* [m] — GENEL model tabanı (TEK KAYNAK)
# -----------------------------------------------------------------------------
# ÖH D18 fizik-a2 (F2 ≡ OH-D15-01): aynı büyüklüğün İKİ ayrı varsayılanı
# vardı ve ikisi ÇELİŞİYORDU —
#   hrma/engines/liquid_rocket_engine.py : L_STAR_DEFAULT_M   = 1.2 m
#   hrma/analysis/kinetic_efficiency.py  : DEFAULT_L_STAR_M   = 1.0 m
# Aynı motorun kalış süresi bir modülde 1,2/c*, diğerinde 1,0/c* çıkıyordu
# (%20 fark) ve kinetik verim bandı bu ikinci sayıdan besleniyordu.
#
# Sayı buraya alındı; her iki modül buradan İTHAL EDER. Bu YALNIZ itici çifti
# SP-125 Tablo 4-1'de OLMAYAN durumların tabanıdır: sıvı motorda çift tabloda
# varsa L* o satırın bandının ortasından gelir (bkz.
# liquid_rocket_engine.L_STAR_BY_PAIR_M).
#
# Kaynak: Huzel & Huang, NASA SP-125 (1971) Böl. IV Tablo 4-1 (s. 87) genel
# aralık 15-120 in = 0,38-3,05 m (kalış süresi 0,002-0,040 s); 1,2 m (47 in)
# bu aralığın içidir ve LOX/RP-1 satırının (40-50 in) hemen üstüdür.
L_STAR_DEFAULT_M = 1.2
L_STAR_GENERIC_BAND_M = (0.38, 3.05)
L_STAR_GENERIC_BAND_SOURCE = (
    'Huzel & Huang, NASA SP-125 (1971) Ch. IV Table 4-1 overall range '
    '15-120 in (0.38-3.05 m), residence time 0.002-0.040 s')


# -----------------------------------------------------------------------------
# Ortam (çevre) sıcaklığı bandı [K] — TEK KAYNAK
# -----------------------------------------------------------------------------
# ÖH D29 app-api-dogrulama a2 (defter P16B1-44). Sayı YENİ DEĞİLDİR: deponun
# kendi fiziksel zarfı ``hrma/engines/hybrid_rocket_engine.py``
# ``_resolve_ambient_temperature`` içinde LİTERAL olarak duruyordu ve
# ``hrma/templates/advanced.html`` #ambient_temp girdisinin min/max'ı
# (180 / 340) onun yankısıydı. Buraya ALINMASININ tek sebebi, ürünün DEĞER
# KAPISININ (``hrma.validation.motor_validation``) aynı sayıyı ikinci kez
# yazmadan okuyabilmesidir (Doktrin 4).
#
# ÖLÇÜLDÜ (``docs/scofield/raw/OH/D29/app-api-dogrulama/a2/once.json`` K1):
# ``ambient_temp`` 14 sarsımın 14'ünde kabul ediliyordu — motor zarfı bant
# dışını SESSİZCE düşürüp ``defaults_used``a not yazıyordu, yani kullanıcının
# gönderdiği sayı uygulanmıyor ama istek de reddedilmiyordu (Doktrin 1:
# beyan çözüm değildir).
#
# Zarfın gerekçesi motorun kendi yorumundan gelir: Dünya yüzeyi çalışma
# bandının cömert bir üst kümesi — Vostok -89,2 °C (183,95 K, 21.07.1983,
# WMO onaylı en düşük yüzey sıcaklığı) ... Ölüm Vadisi +56,7 °C (329,85 K,
# 10.07.1913, WMO onaylı en yüksek). Dışı bir ölçüm değil BİRİM
# KARIŞIKLIĞININ işaretidir (kullanıcı °C girmiş olabilir: 20 °C -> 20 K).
AMBIENT_TEMPERATURE_BAND_K = (180.0, 340.0)
AMBIENT_TEMPERATURE_BAND_SOURCE = (
    'Earth-surface operating envelope, generous superset of the WMO-verified '
    'extremes (Vostok -89.2 C = 183.95 K, 1983-07-21; Death Valley +56.7 C = '
    '329.85 K, 1913-07-10); outside this band the value is a unit mix-up, '
    'not a measurement')


# -----------------------------------------------------------------------------
# Enjektör orifis (delik) çapı tasarım bandı [mm] — TEK KAYNAK
# -----------------------------------------------------------------------------
# ÖH D37 A2 hibrit · F-10 (= CW-A5; YB-03 temizliği). Berke 23 Eyl §9:
# "atölyeye gerek yok, prosedür neyse, en genel olan o" → literatürdeki en
# genel standart, KAYNAKLI tek sabit.
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/A2/hibrit/a1/once/ozet.json K1, Ornek-H1:
# 1000 N, Pc 20 bar, N₂O/HTPB, duş başlığı): aynı büyüklük için depoda DÖRT
# canlı tanım noktası ve ÜÇ farklı bant vardı —
#   hrma/engines/injector_design.py  ORIFICE_D_PREF_MM      (0,5, 2,5) kaynaksız
#   hrma/engines/injector_design.py  DEFAULT_CONSTRAINTS    0,3 / 3,0  kaynaksız
#   hrma/app.py                      uç varsayılanı + çarpışmalı dal 0,3 / 2,0
#   hrma/utils/injector_design.py    imza varsayılanları    0,3 / 2,0  kaynaksız
# ve hrma/validation/validation_system.py'de ölü bir beşinci (0,2/5,0) hiç
# okunmuyordu. Sonuç: devre çözücüsü 3 × Ø2,1115 mm kanon planını "bant içi"
# bulup uyarmıyor, aynı yanıtın utils yolu "outside the manufacturing band
# (0.30-2.00 mm)" yazıyordu — bir plaka, iki hüküm (Cowork A-5'in gördüğü
# uyarı buydu).
#
# Sabit YENİ DEĞİL: ORIFICE_D_PREF_MM zaten (0,5, 2,5) idi. Burada kaynağı
# yazıldı ve diğer tanım noktaları buna BAĞLANDI (engines/utils takma ad +
# sözlük öğesi; app.py yaması).
#
# YAYIMLANAN SAYI (denetçi Ş1 sınıf düzeltmesi — ilk sürüm burada genel
# olarak "sayı değişmez" diyordu, yalnız kanon yolda doğruydu; ölçüm
# docs/scofield/raw/OH/A2/hibrit/a1/sart/once_sonra_s1.json, 18 vaka):
#   * KANON duş başlığı yolunda, toplam orifis alanı A ≥ π·(0,5 mm)²/4
#     ≈ 0,196 mm² iken DEĞİŞMEZ — devre çözücüsünün TERCİH bandı zaten
#     0,5-2,5 idi (Ornek-H1 3 × Ø2,1115 mm bit-aynı).
#   * Devre çözücüsünün SERT kısıtı da değişti (DEFAULT_CONSTRAINTS
#     0,3/3,0 → 0,5/2,5 mm; denetçi-2 Ş-B, ölçüm docs/scofield/raw/OH/A2/
#     hibrit/a1/sart3/sb_*.json): küçük alanlı devrede plan değişir (hibrit
#     kanon 14 N 2 × 0,3086 → 1 × 0,4364 mm; pencere A ∈ [0,141; 0,196)
#     mm²; yankıları chug τ_s, doğrulama uyarıları, CAD ağı), sabit-n /
#     n_max sınırında uyarı SINIFI yükselir (tercih bandı → imalat bandı /
#     plan sağlanamıyor). SIVI motor iki yoldan etkilenir: uyarı sınıfı VE
#     küçük itkide plan (denetçi-3 Ş-3(a): /calculate_liquid 100 N LOX/RP-1,
#     Pc 60, MR 6 yakıt devresi 2 × 0,3287 → 1 × 0,4649 mm; SMD, Rupe,
#     imalat toleransı yankılarıyla) — sıvıda "sayı aynı" GENEL değildir.
#   * Çarpışmalı (impingement) yolda ve kanon-DIŞI duş başlığı yolunda
#     (pressure_drop_source='user' + kullanıcı n_holes; utils doğrudan
#     InjectorDesign çağrısı) eski 0,3/2,0 bandıyla kırpılan/seçilen delik
#     sayısı ve çapı DEĞİŞİR — ör. çarpışmalı 3 kN 8 × 1,881 → 6 × 2,172 mm,
#     kullanıcı ΔP'li n = 400 292 × 0,30 → 105 × 0,50 mm (18 vakanın 9'u).
#     Çarpışmalı KÜÇÜK itkide (Ornek-H1 alanlarıyla ≈104 N altı) çap alt
#     kenara kırpılır ve çift tabanı 2 olduğu için alan istenenin üstüne
#     çıkar (50 N: A 0,378 → 0,785 mm², v 68,75 → 33,12 m/s; denetçi-3
#     Ş-3(c)); bu kırpma denetçi-3 Ş-4'ten beri utils'te adıyla uyarılır.
#   Sınıf: Sunum 2 "yayımlanan sayı değişir" (Berke onayı; berke_onay_A2.md).
#
# Bant bir TASARIM bandıdır, atölye toleransı
# değil: kullanıcı ``hole_diameter_min/max`` ile kendi bandını verirse o
# uygulanır ve ``defaults_applied`` künyesi düşer. Alt uç 0,5 (tıkanma /
# tolerans / C_d verisi 0,5 mm'den başlar), üst uç 2,5 (atomizasyon; C_d
# tabloları 2,5 üstünü ayrı sınıf sayar) — gerekçe belgesi
# docs/scofield/raw/OH/D37/fizik-hazirlik/F10_orifis_bandi.md §3.
#
# Kaynaklar 25 Eylül 2026'da BİRİNCİL metinden doğrulandı (yerel kopyalar;
# Sutton s. 337 §8.9 başlığı altındaki paragraf, Mishra s. 348 madde 1).
# Bekçi: tests/test_sabit_tek_kaynak.py::test_orifis_cap_bandi_kunyesiyle_
# AYNI_araligi_soyluyor (künye "(a.b-c.d mm)" biçimiyle bandın KENDİSİNİ
# söyler — L_STAR_GENERIC_BAND_SOURCE kalıbı; denetçi-3 Ş-1'den beri) +
# tests/test_d37_hibrit_f1.py (kimlik, literal taraması, davranış).
ORIFICE_D_BAND_MM = (0.5, 2.5)
ORIFICE_D_BAND_SOURCE = (
    'Sutton & Biblarz, Rocket Propulsion Elements 9th ed. (Wiley 2017) '
    'Sec. 8.9 "Sample Thrust Chamber Design Analysis", p. 337: "A typical '
    'hole diameter in this size of injector would be between 0.5 to 2.5 mm"; '
    'Mishra, Fundamentals of Rocket Propulsion (CRC Press 2017) Ch. 10, '
    'p. 348: "Orifice hole diameter 0.5-2.5 mm, depending on the size of '
    'rocket engine. The geometric ratio of orifice l/d lies between 2 and 4". '
    'Both verified against the primary texts on 2026-09-25. The band '
    '(0.5-2.5 mm) is a design band, not a shop tolerance')
