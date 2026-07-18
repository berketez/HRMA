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

# ICAO atmosfer hesaplarında kullanılan gaz sabiti (J/(mol*K), CODATA)
R_STAR_ICAO = 8.31432  # J/(mol*K) -- ICAO 1993 tanımı

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

# -----------------------------------------------------------------------------
# Birim Çevirim Sabitleri
# -----------------------------------------------------------------------------
PA_PER_BAR = 1e5  # 1 bar = 100000 Pa
BAR_PER_PA = 1e-5

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


def vacuum_isp_ratio(epsilon: float, gamma: float = 1.22) -> float:
    """Vakum / sea-level Isp oranını expansion ratio'ya bağlı olarak verir.

    1.15 sabit varsayımı yerine, basınç-thrust teriminin epsilon ile orantılı
    katkısını yakalayan birinci-mertebe ampirik korreksiyon. Sutton tablo 3-2
    ile karşılaştırılarak kalibre edilmiştir:
        epsilon=10  -> ~1.05
        epsilon=25  -> ~1.08
        epsilon=40  -> ~1.10
        epsilon=80  -> ~1.13
        epsilon=200 -> ~1.17

    Daha hassas hesap için tam Cf formülü (combustion_analysis veya
    hybrid_rocket_engine içindeki) kullanılmalıdır.
    """
    import numpy as np
    eps = max(float(epsilon), 1.0)
    # Docstring'deki Sutton Tablo 3-2 kalibrasyon noktalarına en küçük kareler
    # fiti: ratio = 0.953 + 0.0405*ln(eps) (maks sapma 0.004, tablo ±0.01 içinde)
    return float(0.953 + 0.0405 * np.log(eps) + 0.005 * (gamma - 1.2))
